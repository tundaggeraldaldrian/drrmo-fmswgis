from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from django.conf import settings
from .models import CustomUser

class CustomUserCreationForm(UserCreationForm):
    """
    Form for regular user registration.
    Staff ID is automatically generated upon user creation.
    Includes date of birth validation (18-80 years old).
    """
    class Meta(UserCreationForm.Meta):
        model = CustomUser
        fields = (
            'username', 'email', 'first_name', 'last_name',
            'position', 'custom_position', 'contact_number', 'date_of_birth',
            'password1', 'password2'
        )
        widgets = {
            'date_of_birth': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        placeholders = {
            'first_name': 'ex. Juan',
            'last_name': 'ex. Dela Cruz',
            'username': 'ex. juandelacruz123',
            'email': 'ex. juan@example.com',
            'position': '-- Select Position --',
            'custom_position': 'ex. Specify your position',
            'contact_number': 'ex. 09123456789',
            'date_of_birth': '',
            'password1': 'ex. SecurePassword123!',
            'password2': 'ex. SecurePassword123!',
        }
        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-control'
            field.required = True
            if field_name in placeholders:
                field.widget.attrs['placeholder'] = placeholders[field_name]
        
        # Custom position is only required when position is "others"
        self.fields['custom_position'].required = False
        
        # Set autofocus on first_name field (first field to fill)
        if 'first_name' in self.fields:
            self.fields['first_name'].widget.attrs['autofocus'] = True
    
    def clean_date_of_birth(self):
        """Validate date of birth: must be 18-80 years old, no future dates."""
        from datetime import date
        
        dob = self.cleaned_data.get('date_of_birth')
        if dob:
            today = date.today()
            
            # Check if date is in the future
            if dob > today:
                raise forms.ValidationError("Date of birth cannot be in the future.")
            
            # Calculate age (accurate method considering leap years)
            age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
            
            # Check minimum age (18)
            if age < 18:
                raise forms.ValidationError("You must be at least 18 years old to register.")
            
            # Check maximum age (80)
            if age > 80:
                raise forms.ValidationError("Age must not exceed 80 years.")
        
        return dob

    def clean_contact_number(self):
        """Validate contact number is exactly 11 digits for registration."""
        num = self.cleaned_data.get('contact_number')
        if num:
            # Remove spaces and common separators
            cleaned = ''.join(filter(str.isdigit, str(num)))
            if len(cleaned) != 11:
                raise forms.ValidationError("Contact number must be exactly 11 digits.")
        return num

    def clean_email(self):
        """Ensure email is unique for registration."""
        email = self.cleaned_data.get('email')
        if email:
            email = email.strip().lower()
        if email and CustomUser.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("This email address is already registered.")
        return email

    def clean(self):
        """Validate that custom_position is provided only when position is 'others'."""
        cleaned_data = super().clean()
        if cleaned_data is None:
            return cleaned_data
        position = cleaned_data.get('position')
        custom_position = cleaned_data.get('custom_position')
        
        # If position is "others", custom_position is required
        if position == 'others':
            if not custom_position or not custom_position.strip():
                self.add_error('custom_position', 'Please specify your position when selecting "Others".')
        else:
            # If position is not "others", clear custom_position
            cleaned_data['custom_position'] = ''
        
        return cleaned_data

class AdminRegistrationForm(UserCreationForm):
    """
    Form for admin registration with secure registration key.
    Staff ID is automatically generated upon user creation.
    Includes date of birth validation (18-80 years old).
    Admin accounts do not require a position field as they are system administrators.
    """
    registration_key = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Enter registration key'}),
        help_text="Enter the secure registration key provided by the system administrator."
    )
    class Meta(UserCreationForm.Meta):
        model = CustomUser
        fields = (
            'username', 'email', 'first_name', 'last_name',
            'contact_number', 'date_of_birth',
            'password1', 'password2'
        )
        widgets = {
            'date_of_birth': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        placeholders = {
            'first_name': 'ex. Juan',
            'last_name': 'ex. Dela Cruz',
            'username': 'ex. admin_user',
            'email': 'ex. admin@example.com',
            'contact_number': 'ex. 09123456789',
            'date_of_birth': '',
            'password1': 'ex. SecurePassword123!',
            'password2': 'ex. SecurePassword123!',
        }
        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-control'
            field.required = True
            if field_name in placeholders:
                field.widget.attrs['placeholder'] = placeholders[field_name]
        
        # Set autofocus on registration_key field (first field to fill)
        if 'registration_key' in self.fields:
            self.fields['registration_key'].widget.attrs['autofocus'] = True
    
    def clean_registration_key(self):
        key = self.cleaned_data.get('registration_key')
        if key != getattr(settings, 'ADMIN_REGISTRATION_KEY', None):
            raise forms.ValidationError("Invalid registration key. Please contact the system administrator.")
        return key
    
    def clean_date_of_birth(self):
        """Validate date of birth: must be 18-80 years old, no future dates."""
        from datetime import date
        
        dob = self.cleaned_data.get('date_of_birth')
        if dob:
            today = date.today()
            
            # Check if date is in the future
            if dob > today:
                raise forms.ValidationError("Date of birth cannot be in the future.")
            
            # Calculate age (accurate method considering leap years)
            age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
            
            # Check minimum age (18)
            if age < 18:
                raise forms.ValidationError("You must be at least 18 years old to register.")
            
            # Check maximum age (80)
            if age > 80:
                raise forms.ValidationError("Age must not exceed 80 years.")
        
        return dob

    def clean_contact_number(self):
        """Validate contact number is exactly 11 digits for admin registration."""
        num = self.cleaned_data.get('contact_number')
        if num:
            cleaned = ''.join(filter(str.isdigit, str(num)))
            if len(cleaned) != 11:
                raise forms.ValidationError("Contact number must be exactly 11 digits.")
        return num

    def clean_email(self):
        """Ensure email is unique for admin registration."""
        email = self.cleaned_data.get('email')
        if email:
            email = email.strip().lower()
        if email and CustomUser.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("This email address is already registered.")
        return email

class ProfileEditForm(UserChangeForm):
    """
    Form for editing user profile information.
    Excludes password field and provides validation for contact numbers and profile image.
    """
    class Meta(UserChangeForm.Meta):
        model = CustomUser
        fields = (  # type: ignore
            'first_name', 'last_name', 'email',
            'position', 'custom_position', 'contact_number',
            'emergency_contact', 'emergency_number',
            'bio', 'date_of_birth', 'profile_image'
        )
        widgets = {
            'date_of_birth': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'bio': forms.Textarea(attrs={'rows': 4, 'class': 'form-control'}),
            'position': forms.Select(attrs={'class': 'form-control'}),
            'profile_image': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'contact_number': forms.TextInput(attrs={'class': 'form-control', 'inputmode': 'numeric', 'pattern': '[0-9]*', 'maxlength': '11'}),
            'emergency_number': forms.TextInput(attrs={'class': 'form-control', 'inputmode': 'numeric', 'pattern': '[0-9]*', 'maxlength': '11'}),
        }
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'password' in self.fields:
            del self.fields['password']
        for field in self.fields.values():
            if not isinstance(field.widget, (forms.CheckboxInput, forms.RadioSelect)):
                if 'class' not in field.widget.attrs:
                    field.widget.attrs['class'] = 'form-control'
        
        # Custom position is only required when position is "others"
        self.fields['custom_position'].required = False
    
    def clean_contact_number(self):
        """Validate contact number: must be exactly 11 digits, digits only."""
        num = self.cleaned_data.get('contact_number')
        if num:
            cleaned = ''.join(filter(str.isdigit, str(num)))
            if len(cleaned) != 11:
                raise forms.ValidationError("Contact number must be exactly 11 digits (numbers only).")
            return cleaned
        return num

    def clean_emergency_number(self):
        """Validate emergency contact number: must be exactly 11 digits, digits only."""
        num = self.cleaned_data.get('emergency_number')
        if num:
            cleaned = ''.join(filter(str.isdigit, str(num)))
            if len(cleaned) != 11:
                raise forms.ValidationError("Emergency contact number must be exactly 11 digits (numbers only).")
            return cleaned
        return num
    
    def clean_date_of_birth(self):
        """Validate date of birth: must be 18-80 years old, no future dates."""
        from datetime import date
        
        dob = self.cleaned_data.get('date_of_birth')
        if dob:
            today = date.today()
            
            # Check if date is in the future
            if dob > today:
                raise forms.ValidationError("Date of birth cannot be in the future.")
            
            # Calculate age (accurate method considering leap years)
            age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
            
            # Check minimum age (18)
            if age < 18:
                raise forms.ValidationError("You must be at least 18 years old.")
            
            # Check maximum age (80)
            if age > 80:
                raise forms.ValidationError("Age must not exceed 80 years.")
        
        return dob
    
    def clean_profile_image(self):
        """Validate profile image file type and size."""
        image = self.cleaned_data.get('profile_image')
        if image:
            # Check file size (max 5MB)
            if image.size > 5 * 1024 * 1024:
                raise forms.ValidationError("Image file size must be less than 5MB.")
            
            # Check file extension
            valid_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp']
            import os
            ext = os.path.splitext(image.name)[1].lower()
            if ext not in valid_extensions:
                raise forms.ValidationError(f"Invalid file type. Allowed types: {', '.join(valid_extensions)}")
            
            # SECURITY: Deep check using Pillow to verify actual image content
            from PIL import Image
            try:
                # We use a context manager or just open/verify
                # Note: verify() doesn't return anything but raises exception on error
                img = Image.open(image)
                img.verify()
            except Exception:
                raise forms.ValidationError("The uploaded file is not a valid image or is corrupted.")
        
        return image
    
    def clean(self):
        """Validate that custom_position is provided only when position is 'others'."""
        cleaned_data = super().clean()
        if cleaned_data is None:
            return cleaned_data
        position = cleaned_data.get('position')
        custom_position = cleaned_data.get('custom_position')
        
        # If position is "others", custom_position is required
        if position == 'others':
            if not custom_position or not custom_position.strip():
                self.add_error('custom_position', 'Please specify your position when selecting "Others".')
        else:
            # If position is not "others", clear custom_position
            cleaned_data['custom_position'] = ''
        
        return cleaned_data