from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

from .models import Question, Quiz, StudentProfile


def _apply_bootstrap_fields(form):
    for field in form.fields.values():
        widget = field.widget
        css_class = "form-select" if isinstance(widget, forms.Select) else "form-control"
        existing = widget.attrs.get("class", "")
        widget.attrs["class"] = f"{existing} {css_class}".strip()


class StudentRegisterForm(forms.Form):
    name = forms.CharField(max_length=150)
    roll_number = forms.CharField(max_length=50)
    year = forms.CharField(max_length=20)
    branch = forms.CharField(max_length=100)
    section = forms.CharField(max_length=20)
    email = forms.EmailField(label="Email ID")
    password = forms.CharField(widget=forms.PasswordInput)
    confirm_password = forms.CharField(widget=forms.PasswordInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _apply_bootstrap_fields(self)

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists() or User.objects.filter(username__iexact=email).exists():
            raise ValidationError("A student with this email ID already exists.")
        return email

    def clean_roll_number(self):
        roll_number = self.cleaned_data["roll_number"].strip()
        if StudentProfile.objects.filter(roll_number__iexact=roll_number).exists():
            raise ValidationError("A student with this roll number already exists.")
        return roll_number

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        confirm_password = cleaned_data.get("confirm_password")
        if password and confirm_password and password != confirm_password:
            self.add_error("confirm_password", "Passwords do not match.")
        return cleaned_data

    def save(self):
        name = self.cleaned_data["name"].strip()
        email = self.cleaned_data["email"]
        user = User.objects.create_user(
            username=email,
            email=email,
            password=self.cleaned_data["password"],
            first_name=name,
        )
        StudentProfile.objects.create(
            user=user,
            roll_number=self.cleaned_data["roll_number"].strip(),
            year=self.cleaned_data["year"].strip(),
            branch=self.cleaned_data["branch"].strip(),
            section=self.cleaned_data["section"].strip(),
        )
        return user


class StudentLoginForm(AuthenticationForm):
    username = forms.EmailField(label="Email ID")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _apply_bootstrap_fields(self)

    def clean(self):
        email = self.cleaned_data.get("username")
        password = self.cleaned_data.get("password")
        if email and password:
            try:
                user = User.objects.get(email__iexact=email, is_staff=False)
            except User.DoesNotExist as exc:
                raise self.get_invalid_login_error() from exc
            self.user_cache = authenticate(
                self.request,
                username=user.username,
                password=password,
            )
            if self.user_cache is None:
                raise self.get_invalid_login_error()
            self.confirm_login_allowed(self.user_cache)
        return self.cleaned_data


class TeacherRegisterForm(forms.Form):
    name = forms.CharField(max_length=150)
    email = forms.EmailField(label="Email ID")
    password = forms.CharField(widget=forms.PasswordInput)
    confirm_password = forms.CharField(widget=forms.PasswordInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _apply_bootstrap_fields(self)

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists() or User.objects.filter(username__iexact=email).exists():
            raise ValidationError("A teacher with this email ID already exists.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        confirm_password = cleaned_data.get("confirm_password")
        if password and confirm_password and password != confirm_password:
            self.add_error("confirm_password", "Passwords do not match.")
        return cleaned_data

    def save(self):
        name = self.cleaned_data["name"].strip()
        email = self.cleaned_data["email"]
        user = User.objects.create_user(
            username=email,
            email=email,
            password=self.cleaned_data["password"],
            first_name=name,
            is_staff=True,
        )
        return user


class TeacherLoginForm(AuthenticationForm):
    username = forms.EmailField(label="Email ID")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _apply_bootstrap_fields(self)

    def clean(self):
        email = self.cleaned_data.get("username")
        password = self.cleaned_data.get("password")
        if email and password:
            try:
                user = User.objects.get(email__iexact=email, is_staff=True)
            except User.DoesNotExist as exc:
                raise self.get_invalid_login_error() from exc
            self.user_cache = authenticate(
                self.request,
                username=user.username,
                password=password,
            )
            if self.user_cache is None:
                raise self.get_invalid_login_error()
            self.confirm_login_allowed(self.user_cache)
        return self.cleaned_data


RegisterForm = StudentRegisterForm


class AccessCodeForm(forms.Form):
    access_code = forms.CharField(max_length=50, required=False, label="Access code")


class QuizFilterForm(forms.Form):
    category = forms.ChoiceField(required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _apply_bootstrap_fields(self)
        categories = (
            Quiz.objects.order_by("category")
            .values_list("category", flat=True)
            .distinct()
        )
        self.fields["category"].choices = [("", "All categories")] + [
            (category, category) for category in categories if category
        ]


class QuizForm(forms.ModelForm):
    class Meta:
        model = Quiz
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
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
            "start_time": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "end_time": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _apply_bootstrap_fields(self)
        self.fields["start_time"].input_formats = ["%Y-%m-%dT%H:%M"]
        self.fields["end_time"].input_formats = ["%Y-%m-%dT%H:%M"]
        self.fields["access_code"].required = False


class QuestionEditorForm(forms.Form):
    text = forms.CharField(widget=forms.Textarea(attrs={"rows": 4}), label="Question")
    option_1 = forms.CharField(max_length=255)
    option_2 = forms.CharField(max_length=255)
    option_3 = forms.CharField(max_length=255)
    option_4 = forms.CharField(max_length=255)
    correct_option = forms.ChoiceField(
        choices=[("1", "Option 1"), ("2", "Option 2"), ("3", "Option 3"), ("4", "Option 4")]
    )

    def __init__(self, *args, question=None, **kwargs):
        self.question = question
        initial = kwargs.pop("initial", {})
        if question and not initial:
            options = list(question.options.order_by("id"))
            initial["text"] = question.text
            for index, option in enumerate(options[:4], start=1):
                initial[f"option_{index}"] = option.text
                if option.is_correct:
                    initial["correct_option"] = str(index)
        super().__init__(*args, initial=initial, **kwargs)
        _apply_bootstrap_fields(self)

    def save(self, quiz):
        if self.question:
            question = self.question
            question.text = self.cleaned_data["text"]
            question.save(update_fields=["text"])
            question.options.all().delete()
        else:
            question = Question.objects.create(quiz=quiz, text=self.cleaned_data["text"])

        correct_option = int(self.cleaned_data["correct_option"])
        for index in range(1, 5):
            question.options.create(
                text=self.cleaned_data[f"option_{index}"],
                is_correct=index == correct_option,
            )
        return question
