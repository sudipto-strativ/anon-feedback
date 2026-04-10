import os

from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from .models import Post, Comment, UserProfile


class MarkdownTextarea(forms.Textarea):
    """Textarea that never renders the HTML required attribute.
    EasyMDE hides this element; a hidden required field blocks form submission
    in Chrome with 'invalid form control is not focusable'."""
    def use_required_attribute(self, initial_value):
        return False


class MultipleFileInput(forms.FileInput):
    allow_multiple_selected = True

    def value_from_datadict(self, data, files, name):
        # Django's FileField.clean() expects a single UploadedFile, not a list.
        # Return only the first file here; clean_attachments() fetches the full
        # list via self.files.getlist() to validate and return all of them.
        file_list = files.getlist(name)
        return file_list[0] if file_list else None

ALLOWED_ATTACHMENT_EXTENSIONS = {
    '.jpg', '.jpeg', '.png', '.gif', '.webp',
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.csv',
}
MAX_ATTACHMENT_SIZE = 10 * 1024 * 1024  # 10 MB
MAX_IMAGE_SIZE = 5 * 1024 * 1024        # 5 MB


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
    attachments = forms.FileField(
        widget=MultipleFileInput(attrs={
            'class': 'form-control',
            'accept': '.jpg,.jpeg,.png,.gif,.webp,.pdf,.doc,.docx,.xls,.xlsx,.csv',
        }),
        required=False,
        help_text='Images, PDF, Word (.doc/.docx), or Excel/CSV. Max 10 MB each.',
    )

    class Meta:
        model = Post
        fields = ['content']
        widgets = {
            'content': MarkdownTextarea(attrs={
                'rows': 5,
                'placeholder': 'Share your anonymous feedback...',
                'class': 'form-control',
            }),
        }

    def clean_attachments(self):
        # request.FILES.getlist returns a list; Django's FileField with multiple
        # input only gives the last file via cleaned_data, so we read from raw
        # files in the view. This clean method validates the single value Django
        # passes here (last selected file) to surface errors early; the view
        # iterates all files itself.
        files = self.files.getlist('attachments')
        for f in files:
            ext = os.path.splitext(f.name)[1].lower()
            if ext not in ALLOWED_ATTACHMENT_EXTENSIONS:
                raise forms.ValidationError(
                    f'"{f.name}" is not an allowed type. '
                    'Accepted: images, PDF, Word, Excel/CSV.'
                )
            if f.size > MAX_ATTACHMENT_SIZE:
                raise forms.ValidationError(
                    f'"{f.name}" exceeds the 10 MB limit.'
                )
        return files


class CommentForm(forms.ModelForm):
    image = forms.ImageField(
        widget=forms.FileInput(attrs={
            'class': 'form-control form-control-sm',
            'accept': 'image/*',
        }),
        required=False,
        help_text='Optional image attachment. Max 5 MB.',
    )

    class Meta:
        model = Comment
        fields = ['content']
        widgets = {
            'content': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'Add your comment… (or attach an image)',
                'class': 'form-control',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['content'].required = False

    def clean(self):
        cleaned_data = super().clean()
        if not cleaned_data.get('content', '').strip() and not cleaned_data.get('image'):
            raise forms.ValidationError('Please add a comment or attach an image.')
        return cleaned_data

    def clean_image(self):
        image = self.cleaned_data.get('image')
        if image and image.size > MAX_IMAGE_SIZE:
            raise forms.ValidationError('Image must be under 5 MB.')
        return image


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
