from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class StudentProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="student_profile")
    roll_number = models.CharField(max_length=50, unique=True)
    year = models.CharField(max_length=20, default="1")
    branch = models.CharField(max_length=100, default="CSE")
    section = models.CharField(max_length=20, default="A")

    class Meta:
        ordering = ["roll_number"]

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.email} ({self.roll_number})"


class Quiz(models.Model):
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="created_quizzes",
        blank=True,
        null=True,
    )
    title = models.CharField(max_length=200)
    description = models.TextField()
    category = models.CharField(max_length=100)
    year = models.CharField(max_length=20, default="1")
    branch = models.CharField(max_length=100, default="CSE")
    section = models.CharField(max_length=20, default="A")
    time_limit = models.PositiveIntegerField(help_text="Time limit in minutes")
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    access_code = models.CharField(max_length=50, blank=True, null=True)

    class Meta:
        ordering = ["start_time", "title"]

    def __str__(self):
        return self.title

    def clean(self):
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValidationError("End time must be after start time.")

    @property
    def is_available(self):
        now = timezone.now()
        return self.start_time <= now <= self.end_time


class Question(models.Model):
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="questions")
    text = models.TextField()

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return self.text[:80]


class Option(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="options")
    text = models.CharField(max_length=255)
    is_correct = models.BooleanField(default=False)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return self.text


class Attempt(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="attempts")
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="attempts")
    score = models.PositiveIntegerField(default=0)
    start_time = models.DateTimeField(default=timezone.now)
    end_time = models.DateTimeField(blank=True, null=True)
    time_taken = models.DurationField(blank=True, null=True)
    tab_switch_count = models.PositiveIntegerField(default=0)
    is_submitted = models.BooleanField(default=False)
    question_order = models.JSONField(default=list, blank=True)
    option_order = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "quiz"], name="unique_user_quiz_attempt")
        ]
        ordering = ["-start_time"]

    def __str__(self):
        return f"{self.user} - {self.quiz}"

    @property
    def deadline(self):
        time_limit_deadline = self.start_time + timezone.timedelta(minutes=self.quiz.time_limit)
        return min(time_limit_deadline, self.quiz.end_time)

    @property
    def has_expired(self):
        return timezone.now() >= self.deadline


class Answer(models.Model):
    attempt = models.ForeignKey(Attempt, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="answers")
    selected_option = models.ForeignKey(Option, on_delete=models.CASCADE, related_name="selected_answers")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["attempt", "question"], name="unique_answer_per_question")
        ]
        ordering = ["question_id"]

    def clean(self):
        if self.question.quiz_id != self.attempt.quiz_id:
            raise ValidationError("Question does not belong to this attempt's quiz.")
        if self.selected_option.question_id != self.question_id:
            raise ValidationError("Selected option does not belong to this question.")

    def __str__(self):
        return f"{self.attempt} - {self.question_id}"
