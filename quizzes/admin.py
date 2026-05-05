import secrets

from django.contrib import admin
from django.core.exceptions import ValidationError
from django.forms.models import BaseInlineFormSet

from .models import Answer, Attempt, Option, Question, Quiz, StudentProfile


class OptionInlineFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        active_forms = [
            form
            for form in self.forms
            if form.cleaned_data and not form.cleaned_data.get("DELETE", False)
        ]
        if len(active_forms) != 4:
            raise ValidationError("Each question must have exactly 4 options.")
        correct_count = sum(1 for form in active_forms if form.cleaned_data.get("is_correct"))
        if correct_count != 1:
            raise ValidationError("Each question must have exactly one correct option.")


class OptionInline(admin.TabularInline):
    model = Option
    formset = OptionInlineFormSet
    extra = 4
    min_num = 4
    max_num = 4
    fields = ("text", "is_correct")


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("text", "quiz")
    list_filter = ("quiz",)
    search_fields = ("text", "quiz__title")
    inlines = [OptionInline]


@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "year", "branch", "section", "time_limit", "start_time", "end_time", "requires_code")
    list_filter = ("category", "year", "branch", "section", "start_time")
    search_fields = ("title", "description", "category", "year", "branch", "section")
    fields = (
        "title",
        "description",
        "category",
        "year",
        "branch",
        "section",
        "time_limit",
        "start_time",
        "end_time",
        "access_code",
    )
    actions = ["generate_access_codes"]

    @admin.display(boolean=True, description="Access code")
    def requires_code(self, obj):
        return bool(obj.access_code)

    @admin.action(description="Generate access codes for selected quizzes")
    def generate_access_codes(self, request, queryset):
        updated = 0
        for quiz in queryset:
            quiz.access_code = secrets.token_urlsafe(6)
            quiz.save(update_fields=["access_code"])
            updated += 1
        self.message_user(request, f"Generated access codes for {updated} quiz(es).")


@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "roll_number", "year", "branch", "section", "email")
    list_filter = ("year", "branch", "section")
    search_fields = ("user__first_name", "user__username", "user__email", "roll_number", "year", "branch", "section")

    @admin.display(description="Email")
    def email(self, obj):
        return obj.user.email


@admin.register(Option)
class OptionAdmin(admin.ModelAdmin):
    list_display = ("text", "question", "is_correct")
    list_filter = ("is_correct", "question__quiz")
    search_fields = ("text", "question__text")


class AnswerInline(admin.TabularInline):
    model = Answer
    extra = 0
    readonly_fields = ("question", "selected_option")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Attempt)
class AttemptAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "quiz",
        "score",
        "start_time",
        "end_time",
        "time_taken",
        "tab_switch_count",
        "fullscreen_exit_count",
        "fullscreen_violation_submitted",
        "is_submitted",
    )
    list_filter = ("quiz", "is_submitted", "start_time")
    search_fields = ("user__username", "quiz__title")
    readonly_fields = (
        "user",
        "quiz",
        "score",
        "start_time",
        "end_time",
        "time_taken",
        "tab_switch_count",
        "fullscreen_exit_count",
        "fullscreen_violation_submitted",
        "is_submitted",
        "question_order",
        "option_order",
    )
    inlines = [AnswerInline]

    def has_add_permission(self, request):
        return False
