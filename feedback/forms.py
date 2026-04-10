from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from .models import Post, Comment, UserProfile


class RegisterForm(UserCreationForm):
    class Meta:
        model = User
        fields = ['username', 'password1', 'password2']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Remove email and any extra fields Django may inject
        self.fields.pop('email', None)
        self.fields.pop('usable_password', None)
        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-control'


class PostForm(forms.ModelForm):
    class Meta:
        model = Post
        fields = ['content']
        widgets = {
            'content': forms.Textarea(attrs={
                'rows': 5,
                'placeholder': 'Share your anonymous feedback...',
                'class': 'form-control',
            }),
        }


class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ['content']
        widgets = {
            'content': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'Add your comment...',
                'class': 'form-control',
            }),
        }


class StatusUpdateForm(forms.ModelForm):
    class Meta:
        model = Post
        fields = ['status', 'eta', 'remark']
        widgets = {
            'status': forms.Select(attrs={'class': 'form-select'}),
            'eta': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'remark': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Required when marking as Done or Rejected — summarise the outcome or reason.',
            }),
        }

    def clean(self):
        cleaned_data = super().clean()
        status = cleaned_data.get('status')
        remark = cleaned_data.get('remark', '').strip()
        if status in ('done', 'rejected') and not remark:
            self.add_error('remark', 'A remark is required when marking a post as Done or Rejected.')
        return cleaned_data
