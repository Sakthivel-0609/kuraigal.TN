from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import Issue, Comment


class IssueForm(forms.ModelForm):
    latitude = forms.FloatField(widget=forms.HiddenInput())
    longitude = forms.FloatField(widget=forms.HiddenInput())

    class Meta:
        model = Issue
        fields = ['title', 'description', 'category', 'address', 'ward', 'latitude', 'longitude',
                  'image', 'is_emergency', 'emergency_type', 'reporter_email', 'is_anonymous']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Large pothole near bus stop'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'category': forms.Select(attrs={'class': 'form-control', 'id': 'id_category'}),
            'address': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Street / landmark'}),
            'ward': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Ward 12 (optional)'}),
            'is_emergency': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'emergency_type': forms.Select(attrs={'class': 'form-select'}),
            'reporter_email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'you@gmail.com'}),
            'is_anonymous': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        is_emergency = cleaned_data.get('is_emergency')
        emergency_type = cleaned_data.get('emergency_type')
        if is_emergency and not emergency_type:
            self.add_error('emergency_type', 'Please select the type of emergency.')
        return cleaned_data

    def clean_image(self):
        image = self.cleaned_data.get('image')
        if image:
            max_size_mb = 5
            if image.size > max_size_mb * 1024 * 1024:
                raise forms.ValidationError(f'Image is too large - please upload a file under {max_size_mb}MB.')
            allowed_types = ['image/jpeg', 'image/png', 'image/webp', 'image/gif']
            content_type = getattr(image, 'content_type', None)
            if content_type and content_type not in allowed_types:
                raise forms.ValidationError('Unsupported image type. Please upload a JPEG, PNG, WEBP, or GIF.')
        return image


class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ['text']
        widgets = {
            'text': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Add a comment...'}),
        }


class SignUpForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({'class': 'form-control'})
