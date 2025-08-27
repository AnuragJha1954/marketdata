from django.shortcuts import render, redirect
from django.utils import timezone
from .models import AuthToken
from .forms import AuthTokenForm

def manage_token(request):
    token_obj = AuthToken.objects.first()  # get the first (and only) token if exists
    last_updated = token_obj.updated_at if token_obj else None

    if request.method == "POST":
        form = AuthTokenForm(request.POST)
        if form.is_valid():
            # delete old token if exists
            AuthToken.objects.all().delete()
            # save new token
            AuthToken.objects.create(
                access_token=form.cleaned_data["access_token"],
                updated_at=timezone.now()
            )
            return redirect("manage_token")
    else:
        form = AuthTokenForm(initial={"access_token": token_obj.access_token if token_obj else ""})

    return render(request, "token.html", {"form": form, "last_updated": last_updated})
