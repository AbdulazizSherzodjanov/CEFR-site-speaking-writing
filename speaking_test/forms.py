from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import Teacher


class RegisterForm(UserCreationForm):
    first_name = forms.CharField(max_length=50, required=True, label="First Name")
    last_name  = forms.CharField(max_length=50, required=True, label="Last Name")
    teacher    = forms.ModelChoiceField(
        queryset=Teacher.objects.filter(is_active=True),
        required=False,
        label="Your Teacher",
        empty_label="-- Select Teacher (Optional) --",
        to_field_name='id',
    )

    class Meta:
        model  = User
        fields = ('first_name', 'last_name', 'username', 'password1', 'password2', 'teacher')

    def save(self, commit=True):
        user = super().save(commit=False)
        user.first_name = self.cleaned_data['first_name']
        user.last_name  = self.cleaned_data['last_name']
        if commit:
            user.save()
        return user
