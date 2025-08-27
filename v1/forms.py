from django import forms

class AuthTokenForm(forms.Form):
    access_token = forms.CharField(widget=forms.Textarea, label="Access Token")
