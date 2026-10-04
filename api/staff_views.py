from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required

from .models import Prescription, Patient


def staff_login(request):

    if request.method == "POST":

        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(request, username=username, password=password)

        if user is not None and user.is_staff:
            login(request, user)
            return redirect("staff_queue")

        return render(request, "staff/login.html", {
            "error": "Invalid credentials or not a staff account."
        })

    return render(request, "staff/login.html")


def staff_logout(request):
    logout(request)
    return redirect("staff_login")


@login_required(login_url="staff_login")
def staff_queue(request):

    query = request.GET.get("q", "").strip()

    patient = None
    prescriptions = Prescription.objects.exclude(status="uploaded").order_by("-created_at")

    if query:
        patient = Patient.objects.filter(token_number__iexact=query).first()

        if patient:
            prescriptions = prescriptions.filter(patient=patient)
        else:
            prescriptions = Prescription.objects.none()

    return render(request, "staff/queue.html", {
        "prescriptions": prescriptions,
        "query": query,
        "patient": patient,
    })


@login_required(login_url="staff_login")
def staff_prescription_detail(request, prescription_id):

    prescription = get_object_or_404(Prescription, id=prescription_id)

    if request.method == "POST" and request.POST.get("action") == "mark_ready":
        prescription.status = "verified"
        prescription.save()
        prescription.medicines.update(pharmacist_verified=True)
        return redirect("staff_prescription_detail", prescription_id=prescription.id)

    return render(request, "staff/prescription_detail.html", {
        "prescription": prescription,
        "medicines": prescription.medicines.all(),
    })