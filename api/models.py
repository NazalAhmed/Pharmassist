from django.db import models

import secrets
import string
from django.utils import timezone
from datetime import timedelta

# Create your models here.
class Patient(models.Model):
    patient_id = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=200, blank=True)
    phone = models.CharField(max_length=20, unique=True)
    token_number = models.CharField(max_length=12, unique=True, editable=False, blank=True)

    address = models.CharField(max_length=300, blank=True)
    age = models.CharField(max_length=50, blank=True)  

    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.token_number:
            self.token_number = self._generate_token()
        super().save(*args, **kwargs)

    @staticmethod
    def _generate_token():
        chars = string.ascii_uppercase + string.digits
        while True:
            candidate = "".join(secrets.choice(chars) for _ in range(8))
            if not Patient.objects.filter(token_number=candidate).exists():
                return candidate

    def __str__(self):
        return f"{self.name or 'Unnamed'} ({self.phone}) - {self.token_number}"

class Medicine(models.Model):
    medicine_name = models.CharField(max_length=200)
    generic_name = models.CharField(max_length=200)
    strength = models.CharField(max_length=50)
    dosage_form = models.CharField(max_length=50)

    available = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["medicine_name"]

    def __str__(self):
        return f"{self.medicine_name} {self.strength}"

class AlternativeMedicine(models.Model):
    medicine = models.ForeignKey(
        Medicine,
        on_delete=models.CASCADE,
        related_name="alternatives"
    )

    alternative_medicine = models.ForeignKey(
        Medicine,
        on_delete=models.CASCADE
    )

    reason = models.CharField(
        max_length=200,
        blank=True
    )

    class Meta:
        unique_together = ("medicine", "alternative_medicine")

    def __str__(self):
        return (
            f"{self.alternative_medicine} "
            f"alternative for {self.medicine}"
        )

class Prescription(models.Model):

    SOURCE_CHOICES = [
        ("patient", "Patient"),
        ("pharmacist", "Pharmacist"),
    ]

    STATUS_CHOICES = [
        ("uploaded", "Uploaded"),
        ("processing", "Processing"),
        ("completed", "Completed"),      # OCR done, awaiting pharmacist
        ("verified", "Verified"),        # pharmacist marked ready
        ("failed", "Failed"),
    ]

    patient = models.ForeignKey(
        Patient,
        on_delete=models.CASCADE,
        related_name="prescriptions",
        null=True,
        blank=True
    )

    source = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    prescription_file = models.FileField(upload_to="prescriptions/")
    extracted_text = models.TextField(blank=True, null=True)

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="uploaded"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    doctor_name = models.CharField(max_length=200, blank=True)
    hospital_name = models.CharField(max_length=200, blank=True)
    op_number = models.CharField(max_length=50, blank=True)
    prescription_date = models.CharField(max_length=50, blank=True)  
    diagnosis = models.CharField(max_length=300, blank=True)

class PrescriptionMedicine(models.Model):

    prescription = models.ForeignKey(
        Prescription,
        on_delete=models.CASCADE,
        related_name="medicines"
    )

    medicine = models.ForeignKey(
        Medicine,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="prescription_records"
    )

    extracted_name = models.CharField(
        max_length=200
    )

    dosage = models.CharField(
        max_length=100,
        blank=True
    )

    frequency = models.CharField(
        max_length=100,
        blank=True
    )

    duration = models.CharField(
        max_length=100,
        blank=True
    )

    confidence_score = models.FloatField(
        null=True,
        blank=True
    )

    pharmacist_verified = models.BooleanField(
        default=False
    )

    quantity = models.CharField(max_length=20, blank=True)  

    def __str__(self):
        return self.extracted_name
