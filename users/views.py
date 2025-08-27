from django.contrib.auth import authenticate, login
from django.shortcuts import render, redirect
from django.contrib import messages
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt

@csrf_exempt
def user_login(request):
    if request.method == "POST":
        email = request.POST.get("email")
        password = request.POST.get("password")
        user = authenticate(request, email=email, password=password)
        if user is not None:
            login(request, user)
            # return redirect("v1/token.html")  # redirect on success
            return redirect(reverse("manage_token"))
        else:
            messages.error(request, "Invalid email or password")
    return render(request, "login.html")

def blank_page(request):
    return render(request, "blank.html")
