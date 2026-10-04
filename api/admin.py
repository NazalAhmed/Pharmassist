from django.contrib import admin
from .models import *

# Register your models here.
admin.site.register(Medicine)
admin.site.register(AlternativeMedicine)
admin.site.register(Prescription)
admin.site.register(PrescriptionMedicine)
admin.site.register(Patient)