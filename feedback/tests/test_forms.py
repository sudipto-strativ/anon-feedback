from io import BytesIO

from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils.datastructures import MultiValueDict
from PIL import Image

from feedback.forms import (
    RegisterForm, PostForm, CommentForm, StatusUpdateForm,
    ALLOWED_ATTACHMENT_EXTENSIONS, MAX_ATTACHMENT_SIZE, MAX_IMAGE_SIZE,
)
from feedback.models import Post
from django.contrib.auth.models import User


def make_user(username='testuser'):
    return User.objects.create_user(username=username, password='pass')


def make_post(author, content='Test', status='pending'):
    return Post.objects.create(author=author, content=content, status=status)


def small_image(name='photo.jpg', size_bytes=None):
    """Create a minimal valid JPEG using Pillow."""
    buf = BytesIO()
    img = Image.new('RGB', (1, 1), color=(255, 0, 0))
    img.save(buf, format='JPEG')
    data = buf.getvalue()
    if size_bytes:
        # Pad to requested size (still valid image — extra bytes ignored by loader)
        data = data + b'\x00' * max(0, size_bytes - len(data))
    return SimpleUploadedFile(name, data, content_type='image/jpeg')


def small_file(name='doc.pdf', size=100):
    return SimpleUploadedFile(name, b'x' * size, content_type='application/pdf')


class RegisterFormTest(TestCase):
    def test_valid_form(self):
        form = RegisterForm(data={
            'username': 'newuser',
            'password1': 'Str0ng!Pass99',
            'password2': 'Str0ng!Pass99',
        })
        self.assertTrue(form.is_valid(), form.errors)

    def test_no_email_field(self):
        form = RegisterForm()
        self.assertNotIn('email', form.fields)

    def test_password_mismatch_invalid(self):
        form = RegisterForm(data={
            'username': 'newuser',
            'password1': 'Str0ng!Pass99',
            'password2': 'Different!Pass99',
        })
        self.assertFalse(form.is_valid())

    def test_duplicate_username_invalid(self):
        User.objects.create_user(username='existing', password='pass')
        form = RegisterForm(data={
            'username': 'existing',
            'password1': 'Str0ng!Pass99',
            'password2': 'Str0ng!Pass99',
        })
        self.assertFalse(form.is_valid())

    def test_form_controls_have_class(self):
        form = RegisterForm()
        for field in form.fields.values():
            self.assertIn('form-control', field.widget.attrs.get('class', ''))


class PostFormTest(TestCase):
    def _make_form(self, content='Hello', files=None):
        data = {'content': content}
        if files is None:
            return PostForm(data=data)
        return PostForm(data=data, files=files)

    def test_valid_no_attachments(self):
        form = self._make_form()
        self.assertTrue(form.is_valid(), form.errors)

    def test_empty_content_invalid(self):
        form = self._make_form(content='')
        self.assertFalse(form.is_valid())

    def test_valid_attachment_pdf(self):
        f = small_file('report.pdf')
        files = MultiValueDict({'attachments': [f]})
        form = PostForm(data={'content': 'Test'}, files=files)
        self.assertTrue(form.is_valid(), form.errors)

    def test_valid_attachment_image(self):
        f = small_image('photo.png')
        files = MultiValueDict({'attachments': [f]})
        form = PostForm(data={'content': 'Test'}, files=files)
        self.assertTrue(form.is_valid(), form.errors)

    def test_invalid_extension_rejected(self):
        f = SimpleUploadedFile('script.exe', b'data', content_type='application/octet-stream')
        files = MultiValueDict({'attachments': [f]})
        form = PostForm(data={'content': 'Test'}, files=files)
        self.assertFalse(form.is_valid())
        self.assertIn('attachments', form.errors)

    def test_oversized_attachment_rejected(self):
        big = SimpleUploadedFile('big.pdf', b'x' * (MAX_ATTACHMENT_SIZE + 1), content_type='application/pdf')
        files = MultiValueDict({'attachments': [big]})
        form = PostForm(data={'content': 'Test'}, files=files)
        self.assertFalse(form.is_valid())
        self.assertIn('attachments', form.errors)

    def test_multiple_valid_attachments(self):
        f1 = small_file('a.pdf')
        f2 = small_image('b.jpg')
        files = MultiValueDict({'attachments': [f1, f2]})
        form = PostForm(data={'content': 'Test'}, files=files)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(len(form.cleaned_data['attachments']), 2)


class CommentFormTest(TestCase):
    def test_content_only_valid(self):
        form = CommentForm(data={'content': 'Nice post'})
        self.assertTrue(form.is_valid(), form.errors)

    def test_image_only_valid(self):
        img = small_image()
        form = CommentForm(data={'content': ''}, files={'image': img})
        self.assertTrue(form.is_valid(), form.errors)

    def test_both_content_and_image_valid(self):
        img = small_image()
        form = CommentForm(data={'content': 'See pic'}, files={'image': img})
        self.assertTrue(form.is_valid(), form.errors)

    def test_neither_content_nor_image_invalid(self):
        form = CommentForm(data={'content': ''})
        self.assertFalse(form.is_valid())
        self.assertIn('__all__', form.errors)

    def test_whitespace_only_content_requires_image(self):
        form = CommentForm(data={'content': '   '})
        self.assertFalse(form.is_valid())

    def test_oversized_image_rejected(self):
        img = small_image()
        img.size = MAX_IMAGE_SIZE + 1  # Fake size to trigger validation without allocating 5 MB
        form = CommentForm(data={'content': 'hi'}, files={'image': img})
        self.assertFalse(form.is_valid())
        self.assertIn('image', form.errors)

    def test_valid_image_size_accepted(self):
        img = small_image()
        form = CommentForm(data={'content': ''}, files={'image': img})
        self.assertTrue(form.is_valid(), form.errors)


class StatusUpdateFormTest(TestCase):
    def setUp(self):
        user = make_user()
        self.post = make_post(user)

    def test_in_progress_no_remark_valid(self):
        form = StatusUpdateForm(
            data={'status': 'in_progress', 'remark': '', 'eta': ''},
            instance=self.post,
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_pending_no_remark_valid(self):
        form = StatusUpdateForm(
            data={'status': 'pending', 'remark': '', 'eta': ''},
            instance=self.post,
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_done_without_remark_invalid(self):
        form = StatusUpdateForm(
            data={'status': 'done', 'remark': '', 'eta': ''},
            instance=self.post,
        )
        self.assertFalse(form.is_valid())
        self.assertIn('remark', form.errors)

    def test_rejected_without_remark_invalid(self):
        form = StatusUpdateForm(
            data={'status': 'rejected', 'remark': '', 'eta': ''},
            instance=self.post,
        )
        self.assertFalse(form.is_valid())
        self.assertIn('remark', form.errors)

    def test_done_with_remark_valid(self):
        form = StatusUpdateForm(
            data={'status': 'done', 'remark': 'Issue resolved', 'eta': ''},
            instance=self.post,
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_rejected_with_remark_valid(self):
        form = StatusUpdateForm(
            data={'status': 'rejected', 'remark': 'Not feasible', 'eta': ''},
            instance=self.post,
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_eta_field_optional(self):
        form = StatusUpdateForm(
            data={'status': 'in_progress', 'remark': '', 'eta': '2025-12-31'},
            instance=self.post,
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(str(form.cleaned_data['eta']), '2025-12-31')
