import csv
import random

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import login
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.db import IntegrityError, transaction
from django.db.models import Avg, Count
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import (
    AccessCodeForm,
    QuestionEditorForm,
    QuizFilterForm,
    QuizForm,
    RegisterForm,
    StudentLoginForm,
    TeacherLoginForm,
    TeacherRegisterForm,
)
from .models import Answer, Attempt, Option, Question, Quiz


def _teacher_quiz_or_404(user, quiz_id):
    return get_object_or_404(Quiz, pk=quiz_id, teacher=user)


class QuizLoginView(LoginView):
    template_name = "registration/login.html"

    def get_success_url(self):
        if self.request.user.is_staff:
            return reverse("teacher_dashboard")
        return reverse("student_dashboard")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.setdefault("login_heading", "Login")
        context.setdefault("submit_label", "Login")
        context.setdefault("show_student_register", True)
        return context


class StudentLoginView(QuizLoginView):
    authentication_form = StudentLoginForm

    def form_valid(self, form):
        user = form.get_user()
        if user.is_staff:
            messages.error(self.request, "Please use teacher login for teacher accounts.")
            return redirect("teacher_login")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("student_dashboard")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "login_heading": "Student login",
                "submit_label": "Login as student",
                "show_student_register": True,
                "alternate_login_label": "Teacher login",
                "alternate_login_url": reverse("teacher_login"),
            }
        )
        return context


class TeacherLoginView(QuizLoginView):
    authentication_form = TeacherLoginForm

    def form_valid(self, form):
        user = form.get_user()
        if not user.is_staff:
            messages.error(self.request, "Please use student login for student accounts.")
            return redirect("student_login")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("teacher_dashboard")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "login_heading": "Teacher login",
                "submit_label": "Login as teacher",
                "show_student_register": False,
                "show_teacher_register": True,
                "alternate_login_label": "Student login",
                "alternate_login_url": reverse("student_login"),
            }
        )
        return context


class QuizLogoutView(LogoutView):
    pass


def register(request):
    if request.user.is_authenticated:
        return redirect("home")
    form = RegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, "Account created. You are now signed in.")
        return redirect("student_dashboard")
    return render(
        request,
        "registration/register.html",
        {
            "form": form,
            "registration_heading": "Student registration",
            "submit_label": "Register as student",
            "login_url": reverse("student_login"),
            "login_label": "Student login",
        },
    )


def teacher_register(request):
    if request.user.is_authenticated:
        return redirect("home")
    form = TeacherRegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, "Teacher account created. You are now signed in.")
        return redirect("teacher_dashboard")
    return render(
        request,
        "registration/register.html",
        {
            "form": form,
            "registration_heading": "Teacher registration",
            "submit_label": "Register as teacher",
            "login_url": reverse("teacher_login"),
            "login_label": "Teacher login",
        },
    )


@login_required
def home(request):
    if request.user.is_staff:
        return redirect("teacher_dashboard")
    return redirect("student_dashboard")


def _available_quizzes():
    now = timezone.now()
    return Quiz.objects.filter(start_time__lte=now, end_time__gte=now)


def _all_class_quizzes_for_student(user):
    profile = getattr(user, "student_profile", None)
    if not profile:
        return Quiz.objects.none()
    return Quiz.objects.filter(
        year__iexact=profile.year,
        branch__iexact=profile.branch,
        section__iexact=profile.section,
    )


def _quizzes_for_student(user):
    quizzes = _available_quizzes()
    profile = getattr(user, "student_profile", None)
    if not profile:
        return quizzes.none()
    return quizzes.filter(
        year__iexact=profile.year,
        branch__iexact=profile.branch,
        section__iexact=profile.section,
    )


def _student_can_access_quiz(user, quiz):
    profile = getattr(user, "student_profile", None)
    if not profile:
        return False
    return (
        quiz.year.lower() == profile.year.lower()
        and quiz.branch.lower() == profile.branch.lower()
        and quiz.section.lower() == profile.section.lower()
    )


def _student_can_view_leaderboard(user, quiz):
    if user.is_staff:
        return quiz.teacher_id == user.id
    return _student_can_access_quiz(user, quiz)


def _quiz_is_ready(quiz):
    questions = quiz.questions.prefetch_related("options")
    if not questions.exists():
        return False, "This quiz has no questions yet."
    for question in questions:
        options = list(question.options.all())
        if len(options) != 4:
            return False, "Every question must have exactly 4 options."
        if sum(1 for option in options if option.is_correct) != 1:
            return False, "Every question must have exactly one correct option."
    return True, ""


def _build_random_order(quiz):
    questions = list(quiz.questions.values_list("id", flat=True))
    random.shuffle(questions)
    option_order = {}
    for question_id in questions:
        option_ids = list(Option.objects.filter(question_id=question_id).values_list("id", flat=True))
        random.shuffle(option_ids)
        option_order[str(question_id)] = option_ids
    return questions, option_order


def _finalize_attempt(attempt):
    attempt.refresh_from_db()
    if attempt.is_submitted:
        return attempt

    finish_time = min(timezone.now(), attempt.deadline)
    score = Answer.objects.filter(attempt=attempt, selected_option__is_correct=True).count()
    attempt.score = score
    attempt.end_time = finish_time
    attempt.time_taken = finish_time - attempt.start_time
    attempt.is_submitted = True
    attempt.save(update_fields=["score", "end_time", "time_taken", "is_submitted"])
    return attempt


def _ensure_active_attempt(attempt):
    if attempt.is_submitted:
        return False
    if attempt.has_expired or not attempt.quiz.is_available:
        _finalize_attempt(attempt)
        return False
    return True


@login_required
def student_dashboard(request):
    if request.user.is_staff:
        return redirect("teacher_dashboard")
    form = QuizFilterForm(request.GET or None)
    quizzes = _quizzes_for_student(request.user).order_by("category", "title")
    if form.is_valid() and form.cleaned_data.get("category"):
        quizzes = quizzes.filter(category=form.cleaned_data["category"])

    attempts = Attempt.objects.filter(user=request.user, quiz__in=quizzes)
    attempt_map = {attempt.quiz_id: attempt for attempt in attempts}
    quiz_rows = [{"quiz": quiz, "attempt": attempt_map.get(quiz.id)} for quiz in quizzes]
    all_class_quizzes = _all_class_quizzes_for_student(request.user)
    all_attempts = Attempt.objects.filter(user=request.user).select_related("quiz")
    completed_attempts = all_attempts.filter(is_submitted=True)
    upcoming_quizzes = all_class_quizzes.filter(start_time__gt=timezone.now()).order_by("start_time")[:5]
    active_quiz_count = _quizzes_for_student(request.user).count()

    return render(
        request,
        "quizzes/student_dashboard.html",
        {
            "form": form,
            "quiz_rows": quiz_rows,
            "now": timezone.now(),
            "all_attempts": all_attempts,
            "completed_attempts": completed_attempts,
            "upcoming_quizzes": upcoming_quizzes,
            "active_quiz_count": active_quiz_count,
        },
    )


@login_required
def quiz_list(request):
    if request.user.is_staff:
        return redirect("teacher_dashboard")
    form = QuizFilterForm(request.GET or None)
    quizzes = _quizzes_for_student(request.user).order_by("category", "title")
    if form.is_valid() and form.cleaned_data.get("category"):
        quizzes = quizzes.filter(category=form.cleaned_data["category"])
    attempts = Attempt.objects.filter(user=request.user, quiz__in=quizzes)
    attempt_map = {attempt.quiz_id: attempt for attempt in attempts}
    quiz_rows = [{"quiz": quiz, "attempt": attempt_map.get(quiz.id)} for quiz in quizzes]
    return render(request, "quizzes/student_quiz_list.html", {"form": form, "quiz_rows": quiz_rows})


@login_required
def student_upcoming_quizzes(request):
    if request.user.is_staff:
        return redirect("teacher_dashboard")
    quizzes = _all_class_quizzes_for_student(request.user).filter(start_time__gt=timezone.now()).order_by("start_time")
    return render(request, "quizzes/student_upcoming.html", {"quizzes": quizzes})


@login_required
def student_results(request):
    if request.user.is_staff:
        return redirect("teacher_dashboard")
    attempts = (
        Attempt.objects.filter(user=request.user, is_submitted=True)
        .select_related("quiz")
        .order_by("-end_time")
    )
    return render(request, "quizzes/student_results.html", {"attempts": attempts})


@login_required
def student_leaderboards(request):
    if request.user.is_staff:
        return redirect("teacher_dashboard")
    quizzes = _all_class_quizzes_for_student(request.user).order_by("-start_time", "title")
    return render(request, "quizzes/student_leaderboards.html", {"quizzes": quizzes})


@login_required
def quiz_instruction(request, quiz_id):
    if request.user.is_staff:
        messages.info(request, "Teacher accounts manage quizzes from the teacher dashboard.")
        return redirect("teacher_dashboard")
    quiz = get_object_or_404(Quiz, pk=quiz_id)
    if not _student_can_access_quiz(request.user, quiz):
        messages.error(request, "This quiz is not assigned to your year, branch, and section.")
        return redirect("student_dashboard")
    existing_attempt = Attempt.objects.filter(user=request.user, quiz=quiz).first()
    access_form = AccessCodeForm()
    ready, readiness_error = _quiz_is_ready(quiz)

    return render(
        request,
        "quizzes/instructions.html",
        {
            "quiz": quiz,
            "access_form": access_form,
            "existing_attempt": existing_attempt,
            "ready": ready,
            "readiness_error": readiness_error,
        },
    )


@login_required
@require_POST
def start_quiz(request, quiz_id):
    if request.user.is_staff:
        messages.error(request, "Teacher accounts cannot take student quizzes.")
        return redirect("teacher_dashboard")
    quiz = get_object_or_404(Quiz, pk=quiz_id)
    if not _student_can_access_quiz(request.user, quiz):
        messages.error(request, "This quiz is not assigned to your year, branch, and section.")
        return redirect("student_dashboard")
    if not quiz.is_available:
        messages.error(request, "This quiz is not available right now.")
        return redirect("quiz_instruction", quiz_id=quiz.id)

    existing_attempt = Attempt.objects.filter(user=request.user, quiz=quiz).first()
    if existing_attempt:
        if existing_attempt.is_submitted:
            messages.warning(request, "You have already submitted this quiz.")
            return redirect("result", attempt_id=existing_attempt.id)
        return redirect("attempt_question", attempt_id=existing_attempt.id, position=1)

    form = AccessCodeForm(request.POST)
    if quiz.access_code and (not form.is_valid() or form.cleaned_data["access_code"] != quiz.access_code):
        messages.error(request, "Invalid access code.")
        return redirect("quiz_instruction", quiz_id=quiz.id)

    ready, readiness_error = _quiz_is_ready(quiz)
    if not ready:
        messages.error(request, readiness_error)
        return redirect("quiz_instruction", quiz_id=quiz.id)

    question_order, option_order = _build_random_order(quiz)
    try:
        with transaction.atomic():
            attempt = Attempt.objects.create(
                user=request.user,
                quiz=quiz,
                question_order=question_order,
                option_order=option_order,
            )
    except IntegrityError:
        attempt = Attempt.objects.get(user=request.user, quiz=quiz)
        messages.warning(request, "An attempt already exists for this quiz.")

    return redirect("attempt_question", attempt_id=attempt.id, position=1)


@login_required
def attempt_question(request, attempt_id, position):
    if request.user.is_staff:
        messages.error(request, "Teacher accounts cannot take student quizzes.")
        return redirect("teacher_dashboard")
    attempt = get_object_or_404(
        Attempt.objects.select_related("quiz", "user"), pk=attempt_id, user=request.user
    )
    if not _ensure_active_attempt(attempt):
        messages.info(request, "Your quiz attempt has ended.")
        return redirect("result", attempt_id=attempt.id)

    question_ids = attempt.question_order
    total_questions = len(question_ids)
    if position < 1 or position > total_questions:
        raise Http404("Question page not found.")

    question_id = question_ids[position - 1]
    question = get_object_or_404(Question, pk=question_id, quiz=attempt.quiz)
    option_ids = attempt.option_order.get(str(question_id), [])
    options_by_id = Option.objects.in_bulk(option_ids)
    options = [options_by_id[option_id] for option_id in option_ids if option_id in options_by_id]
    selected_answer = Answer.objects.filter(attempt=attempt, question=question).first()
    remaining_seconds = max(0, int((attempt.deadline - timezone.now()).total_seconds()))

    return render(
        request,
        "quizzes/attempt.html",
        {
            "attempt": attempt,
            "quiz": attempt.quiz,
            "question": question,
            "options": options,
            "selected_answer": selected_answer,
            "position": position,
            "total_questions": total_questions,
            "remaining_seconds": remaining_seconds,
            "previous_position": position - 1 if position > 1 else None,
            "next_position": position + 1 if position < total_questions else None,
        },
    )


@login_required
@require_POST
def save_answer(request, attempt_id):
    attempt = get_object_or_404(Attempt.objects.select_related("quiz"), pk=attempt_id, user=request.user)
    if not _ensure_active_attempt(attempt):
        return JsonResponse({"saved": False, "expired": True, "redirect_url": reverse("result", args=[attempt.id])})

    question_id = request.POST.get("question_id")
    option_id = request.POST.get("option_id")
    if not question_id or not option_id:
        return JsonResponse({"saved": False, "error": "Missing answer data."}, status=400)

    try:
        question_id_int = int(question_id)
    except (TypeError, ValueError):
        return JsonResponse({"saved": False, "error": "Invalid question."}, status=400)

    if question_id_int not in attempt.question_order:
        return JsonResponse({"saved": False, "error": "Invalid question."}, status=400)

    question = get_object_or_404(Question, pk=question_id_int, quiz=attempt.quiz)
    option = get_object_or_404(Option, pk=option_id, question=question)
    Answer.objects.update_or_create(
        attempt=attempt,
        question=question,
        defaults={"selected_option": option},
    )
    return JsonResponse({"saved": True, "expired": False})


@login_required
@require_POST
def log_tab_switch(request, attempt_id):
    attempt = get_object_or_404(Attempt, pk=attempt_id, user=request.user)
    if not _ensure_active_attempt(attempt):
        return JsonResponse({"logged": False, "expired": True, "redirect_url": reverse("result", args=[attempt.id])})
    attempt.tab_switch_count += 1
    attempt.save(update_fields=["tab_switch_count"])
    return JsonResponse({"logged": True, "tab_switch_count": attempt.tab_switch_count})


@login_required
@require_POST
def submit_attempt(request, attempt_id):
    attempt = get_object_or_404(Attempt, pk=attempt_id, user=request.user)
    _finalize_attempt(attempt)
    messages.success(request, "Quiz submitted successfully.")
    return redirect("result", attempt_id=attempt.id)


@login_required
def result(request, attempt_id):
    attempt = get_object_or_404(
        Attempt.objects.select_related("quiz", "user").prefetch_related("answers"),
        pk=attempt_id,
        user=request.user,
    )
    if not attempt.is_submitted:
        if attempt.has_expired:
            _finalize_attempt(attempt)
        else:
            messages.info(request, "Finish the quiz before viewing results.")
            return redirect("attempt_question", attempt_id=attempt.id, position=1)

    answers_by_question = {
        answer.question_id: answer
        for answer in Answer.objects.filter(attempt=attempt).select_related("selected_option")
    }
    review_rows = []
    correct_count = 0
    for question_id in attempt.question_order:
        question = Question.objects.get(pk=question_id)
        correct_option = question.options.get(is_correct=True)
        answer = answers_by_question.get(question.id)
        is_correct = bool(answer and answer.selected_option_id == correct_option.id)
        correct_count += 1 if is_correct else 0
        review_rows.append(
            {
                "question": question,
                "user_option": answer.selected_option if answer else None,
                "correct_option": correct_option,
                "is_correct": is_correct,
            }
        )

    total_questions = len(attempt.question_order)
    wrong_count = total_questions - correct_count
    percentage = (correct_count / total_questions * 100) if total_questions else 0

    return render(
        request,
        "quizzes/result.html",
        {
            "attempt": attempt,
            "total_questions": total_questions,
            "correct_count": correct_count,
            "wrong_count": wrong_count,
            "percentage": percentage,
            "review_rows": review_rows,
        },
    )


@login_required
def leaderboard(request, quiz_id):
    quiz = get_object_or_404(Quiz, pk=quiz_id)
    if not _student_can_view_leaderboard(request.user, quiz):
        messages.error(request, "You do not have access to this leaderboard.")
        return redirect("home")
    attempts = (
        Attempt.objects.filter(quiz=quiz, is_submitted=True)
        .select_related("user")
        .order_by("-score", "time_taken", "end_time")
    )
    ranked_attempts = [
        {"rank": index + 1, "attempt": attempt}
        for index, attempt in enumerate(attempts)
    ]
    return render(request, "quizzes/leaderboard.html", {"quiz": quiz, "ranked_attempts": ranked_attempts})


@staff_member_required(login_url="teacher_login")
def teacher_dashboard(request):
    teacher_quizzes = Quiz.objects.filter(teacher=request.user)
    attempts = Attempt.objects.filter(is_submitted=True, quiz__in=teacher_quizzes)
    analytics = attempts.aggregate(total_attempts=Count("id"), average_score=Avg("score"))
    recent_attempts = attempts.select_related("user", "user__student_profile", "quiz").order_by("-end_time")[:20]
    now = timezone.now()
    total_quizzes = teacher_quizzes.count()
    active_quizzes = teacher_quizzes.filter(start_time__lte=now, end_time__gte=now).count()
    upcoming_quizzes = teacher_quizzes.filter(start_time__gt=now).order_by("start_time")[:5]
    completed_quizzes = teacher_quizzes.filter(end_time__lt=now).count()
    students = (
        User.objects.filter(attempts__quiz__in=teacher_quizzes, is_staff=False, is_superuser=False)
        .select_related("student_profile")
        .annotate(total_attempts=Count("attempts"))
        .distinct()
        .order_by("-date_joined")
    )
    return render(
        request,
        "quizzes/teacher_dashboard.html",
        {
            "analytics": analytics,
            "recent_attempts": recent_attempts,
            "total_quizzes": total_quizzes,
            "active_quizzes": active_quizzes,
            "upcoming_quizzes": upcoming_quizzes,
            "completed_quizzes": completed_quizzes,
            "students": students,
        },
    )


@staff_member_required(login_url="teacher_login")
def admin_dashboard(request):
    return redirect("teacher_dashboard")


@staff_member_required(login_url="teacher_login")
def teacher_quiz_list(request):
    quizzes = (
        Quiz.objects.filter(teacher=request.user)
        .annotate(total_attempts=Count("attempts"))
        .order_by("-start_time", "title")
    )
    return render(request, "quizzes/teacher_quiz_list.html", {"quizzes": quizzes})


@staff_member_required(login_url="teacher_login")
def teacher_student_list(request):
    teacher_quizzes = Quiz.objects.filter(teacher=request.user)
    students = (
        User.objects.filter(attempts__quiz__in=teacher_quizzes, is_staff=False, is_superuser=False)
        .select_related("student_profile")
        .annotate(total_attempts=Count("attempts"))
        .distinct()
        .order_by("student_profile__roll_number", "first_name")
    )
    return render(request, "quizzes/teacher_student_list.html", {"students": students})


@staff_member_required(login_url="teacher_login")
def teacher_results_overview(request):
    attempts = (
        Attempt.objects.filter(is_submitted=True, quiz__teacher=request.user)
        .select_related("user", "user__student_profile", "quiz")
        .order_by("quiz__title", "-score", "time_taken")
    )
    quizzes = Quiz.objects.filter(teacher=request.user).annotate(total_attempts=Count("attempts")).order_by("title")
    return render(
        request,
        "quizzes/teacher_results_overview.html",
        {"attempts": attempts, "quizzes": quizzes},
    )


@staff_member_required(login_url="teacher_login")
def teacher_quiz_create(request):
    form = QuizForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        quiz = form.save(commit=False)
        quiz.teacher = request.user
        quiz.save()
        messages.success(request, "Quiz created. Add questions now.")
        return redirect("teacher_question_list", quiz_id=quiz.id)
    return render(
        request,
        "quizzes/teacher_quiz_form.html",
        {"form": form, "heading": "Add quiz", "submit_label": "Save quiz"},
    )


@staff_member_required(login_url="teacher_login")
def teacher_quiz_update(request, quiz_id):
    quiz = _teacher_quiz_or_404(request.user, quiz_id)
    form = QuizForm(request.POST or None, instance=quiz)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Quiz updated.")
        return redirect("teacher_dashboard")
    return render(
        request,
        "quizzes/teacher_quiz_form.html",
        {"form": form, "quiz": quiz, "heading": "Edit quiz", "submit_label": "Update quiz"},
    )


@staff_member_required(login_url="teacher_login")
def teacher_quiz_delete(request, quiz_id):
    quiz = _teacher_quiz_or_404(request.user, quiz_id)
    if request.method == "POST":
        quiz.delete()
        messages.success(request, "Quiz deleted.")
        return redirect("teacher_dashboard")
    return render(
        request,
        "quizzes/confirm_delete.html",
        {"object_name": quiz.title, "cancel_url": reverse("teacher_dashboard")},
    )


@staff_member_required(login_url="teacher_login")
def teacher_question_list(request, quiz_id):
    quiz = _teacher_quiz_or_404(request.user, quiz_id)
    questions = quiz.questions.prefetch_related("options").order_by("id")
    return render(
        request,
        "quizzes/teacher_question_list.html",
        {"quiz": quiz, "questions": questions},
    )


@staff_member_required(login_url="teacher_login")
def teacher_question_create(request, quiz_id):
    quiz = _teacher_quiz_or_404(request.user, quiz_id)
    form = QuestionEditorForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save(quiz=quiz)
        messages.success(request, "Question added.")
        return redirect("teacher_question_list", quiz_id=quiz.id)
    return render(
        request,
        "quizzes/teacher_question_form.html",
        {"form": form, "quiz": quiz, "heading": "Add question", "submit_label": "Save question"},
    )


@staff_member_required(login_url="teacher_login")
def teacher_question_update(request, quiz_id, question_id):
    quiz = _teacher_quiz_or_404(request.user, quiz_id)
    question = get_object_or_404(Question, pk=question_id, quiz=quiz)
    form = QuestionEditorForm(request.POST or None, question=question)
    if request.method == "POST" and form.is_valid():
        form.save(quiz=quiz)
        messages.success(request, "Question updated.")
        return redirect("teacher_question_list", quiz_id=quiz.id)
    return render(
        request,
        "quizzes/teacher_question_form.html",
        {"form": form, "quiz": quiz, "question": question, "heading": "Edit question", "submit_label": "Update question"},
    )


@staff_member_required(login_url="teacher_login")
def teacher_question_delete(request, quiz_id, question_id):
    quiz = _teacher_quiz_or_404(request.user, quiz_id)
    question = get_object_or_404(Question, pk=question_id, quiz=quiz)
    if request.method == "POST":
        question.delete()
        messages.success(request, "Question deleted.")
        return redirect("teacher_question_list", quiz_id=quiz.id)
    return render(
        request,
        "quizzes/confirm_delete.html",
        {"object_name": question.text[:80], "cancel_url": reverse("teacher_question_list", args=[quiz.id])},
    )


@staff_member_required(login_url="teacher_login")
def teacher_quiz_results(request, quiz_id):
    quiz = _teacher_quiz_or_404(request.user, quiz_id)
    attempts = (
        Attempt.objects.filter(quiz=quiz, is_submitted=True)
        .select_related("user", "user__student_profile")
        .order_by("-score", "time_taken", "end_time")
    )
    return render(
        request,
        "quizzes/teacher_quiz_results.html",
        {"quiz": quiz, "attempts": attempts},
    )


@staff_member_required(login_url="teacher_login")
def export_results_csv(request):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="quiz_results.csv"'
    writer = csv.writer(response)
    writer.writerow(
        [
            "Quiz",
            "Category",
            "Student name",
            "Roll number",
            "Year",
            "Branch",
            "Section",
            "Email",
            "Score",
            "Start time",
            "End time",
            "Time taken",
            "Tab switches",
        ]
    )
    attempts = (
        Attempt.objects.filter(is_submitted=True, quiz__teacher=request.user)
        .select_related("quiz", "user", "user__student_profile")
        .order_by("quiz__title", "-score")
    )
    for attempt in attempts:
        profile = getattr(attempt.user, "student_profile", None)
        writer.writerow(
            [
                attempt.quiz.title,
                attempt.quiz.category,
                attempt.user.get_full_name() or attempt.user.username,
                profile.roll_number if profile else "",
                profile.year if profile else "",
                profile.branch if profile else "",
                profile.section if profile else "",
                attempt.user.email,
                attempt.score,
                attempt.start_time,
                attempt.end_time,
                attempt.time_taken,
                attempt.tab_switch_count,
            ]
        )
    return response


@staff_member_required(login_url="teacher_login")
def export_quiz_results_csv(request, quiz_id):
    quiz = _teacher_quiz_or_404(request.user, quiz_id)
    response = HttpResponse(content_type="text/csv")
    filename = f"{quiz.title.lower().replace(' ', '_')}_results.csv"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)
    writer.writerow(
        [
            "Quiz",
            "Category",
            "Student name",
            "Roll number",
            "Year",
            "Branch",
            "Section",
            "Email",
            "Score",
            "Total questions",
            "Percentage",
            "Start time",
            "End time",
            "Time taken",
            "Tab switches",
        ]
    )
    total_questions = quiz.questions.count()
    attempts = (
        Attempt.objects.filter(quiz=quiz, is_submitted=True)
        .select_related("user", "user__student_profile")
        .order_by("-score", "time_taken", "end_time")
    )
    for attempt in attempts:
        percentage = (attempt.score / total_questions * 100) if total_questions else 0
        profile = getattr(attempt.user, "student_profile", None)
        writer.writerow(
            [
                quiz.title,
                quiz.category,
                attempt.user.get_full_name() or attempt.user.username,
                profile.roll_number if profile else "",
                profile.year if profile else "",
                profile.branch if profile else "",
                profile.section if profile else "",
                attempt.user.email,
                attempt.score,
                total_questions,
                f"{percentage:.2f}",
                attempt.start_time,
                attempt.end_time,
                attempt.time_taken,
                attempt.tab_switch_count,
            ]
        )
    return response
