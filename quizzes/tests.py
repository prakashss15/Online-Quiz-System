from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Answer, Attempt, Option, Question, Quiz, StudentProfile


class QuizFlowTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(
            username="teacher@example.com",
            email="teacher@example.com",
            password="pass12345",
            is_staff=True,
        )
        self.user = User.objects.create_user(username="student", password="pass12345")
        self.other_user = User.objects.create_user(username="fast", password="pass12345")
        now = timezone.now()
        self.quiz = Quiz.objects.create(
            teacher=self.teacher,
            title="Python Basics",
            description="Core Python quiz",
            category="Programming",
            year="2",
            branch="CSE",
            section="A",
            time_limit=10,
            start_time=now - timezone.timedelta(minutes=5),
            end_time=now + timezone.timedelta(hours=1),
            access_code="OPEN",
        )
        StudentProfile.objects.create(
            user=self.user,
            roll_number="R000",
            year="2",
            branch="CSE",
            section="A",
        )
        self.question = Question.objects.create(quiz=self.quiz, text="What is Django?")
        self.correct = Option.objects.create(question=self.question, text="A web framework", is_correct=True)
        for text in ["A database", "An operating system", "A browser"]:
            Option.objects.create(question=self.question, text=text, is_correct=False)

    def test_attempt_autosaves_submits_and_blocks_retake(self):
        self.client.login(username="student", password="pass12345")
        response = self.client.post(reverse("start_quiz", args=[self.quiz.id]), {"access_code": "OPEN"})
        self.assertEqual(response.status_code, 302)

        attempt = Attempt.objects.get(user=self.user, quiz=self.quiz)
        save_response = self.client.post(
            reverse("save_answer", args=[attempt.id]),
            {"question_id": self.question.id, "option_id": self.correct.id},
        )
        self.assertJSONEqual(save_response.content, {"saved": True, "expired": False})
        self.assertEqual(Answer.objects.filter(attempt=attempt).count(), 1)

        self.client.post(reverse("submit_attempt", args=[attempt.id]))
        attempt.refresh_from_db()
        self.assertTrue(attempt.is_submitted)
        self.assertEqual(attempt.score, 1)

        self.client.post(reverse("start_quiz", args=[self.quiz.id]), {"access_code": "OPEN"})
        self.assertEqual(Attempt.objects.filter(user=self.user, quiz=self.quiz).count(), 1)

    def test_leaderboard_orders_by_score_then_time_taken(self):
        slow = Attempt.objects.create(
            user=self.user,
            quiz=self.quiz,
            score=1,
            start_time=timezone.now(),
            end_time=timezone.now() + timezone.timedelta(minutes=5),
            time_taken=timezone.timedelta(minutes=5),
            is_submitted=True,
        )
        fast = Attempt.objects.create(
            user=self.other_user,
            quiz=self.quiz,
            score=1,
            start_time=timezone.now(),
            end_time=timezone.now() + timezone.timedelta(minutes=2),
            time_taken=timezone.timedelta(minutes=2),
            is_submitted=True,
        )
        self.client.login(username="student", password="pass12345")
        response = self.client.get(reverse("leaderboard", args=[self.quiz.id]))
        attempts = [row["attempt"] for row in response.context["ranked_attempts"]]
        self.assertEqual(attempts, [fast, slow])

    def test_student_registers_with_email_and_logs_in_with_email(self):
        response = self.client.post(
            reverse("student_register"),
            {
                "name": "Anu Student",
                "roll_number": "CSE001",
                "year": "2",
                "branch": "CSE",
                "section": "A",
                "email": "anu@example.com",
                "password": "pass12345",
                "confirm_password": "pass12345",
            },
        )
        self.assertRedirects(response, reverse("student_dashboard"))
        user = User.objects.get(email="anu@example.com")
        self.assertEqual(user.username, "anu@example.com")
        self.assertEqual(user.first_name, "Anu Student")
        self.assertEqual(user.student_profile.roll_number, "CSE001")
        self.assertEqual(user.student_profile.year, "2")
        self.assertEqual(user.student_profile.branch, "CSE")
        self.assertEqual(user.student_profile.section, "A")

        self.client.logout()
        login_response = self.client.post(
            reverse("student_login"),
            {"username": "anu@example.com", "password": "pass12345"},
        )
        self.assertRedirects(login_response, reverse("student_dashboard"))

    def test_teacher_can_export_quiz_wise_report(self):
        self.user.first_name = "Test Student"
        self.user.email = "student@example.com"
        self.user.save()
        self.user.student_profile.roll_number = "R001"
        self.user.student_profile.save()
        Attempt.objects.create(
            user=self.user,
            quiz=self.quiz,
            score=1,
            start_time=timezone.now(),
            end_time=timezone.now() + timezone.timedelta(minutes=1),
            time_taken=timezone.timedelta(minutes=1),
            is_submitted=True,
        )

        self.client.login(username="teacher@example.com", password="pass12345")
        response = self.client.get(reverse("export_quiz_results_csv", args=[self.quiz.id]))
        self.assertEqual(response.status_code, 200)
        self.assertIn("Python Basics", response.content.decode())
        self.assertIn("R001", response.content.decode())

    def test_teacher_registers_from_teacher_registration_page(self):
        response = self.client.post(
            reverse("teacher_register"),
            {
                "name": "Teacher One",
                "email": "teacher.one@example.com",
                "password": "pass12345",
                "confirm_password": "pass12345",
            },
        )
        self.assertRedirects(response, reverse("teacher_dashboard"))
        teacher = User.objects.get(email="teacher.one@example.com")
        self.assertTrue(teacher.is_staff)
        self.assertEqual(teacher.username, "teacher.one@example.com")

    def test_teacher_creates_quiz_and_question_without_django_admin(self):
        self.client.login(username="teacher@example.com", password="pass12345")
        response = self.client.post(
            reverse("teacher_quiz_create"),
            {
                "title": "DBMS Test",
                "description": "Database quiz",
                "category": "DBMS",
                "year": "3",
                "branch": "CSE",
                "section": "B",
                "time_limit": "15",
                "start_time": (timezone.now() + timezone.timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M"),
                "end_time": (timezone.now() + timezone.timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M"),
                "access_code": "",
            },
        )
        quiz = Quiz.objects.get(title="DBMS Test")
        self.assertRedirects(response, reverse("teacher_question_list", args=[quiz.id]))
        self.assertEqual(quiz.teacher, self.teacher)

        question_response = self.client.post(
            reverse("teacher_question_create", args=[quiz.id]),
            {
                "text": "What is SQL?",
                "option_1": "Query language",
                "option_2": "Operating system",
                "option_3": "Browser",
                "option_4": "Compiler",
                "correct_option": "1",
            },
        )
        self.assertRedirects(question_response, reverse("teacher_question_list", args=[quiz.id]))
        self.assertEqual(quiz.questions.count(), 1)
        self.assertEqual(quiz.questions.first().options.count(), 4)
