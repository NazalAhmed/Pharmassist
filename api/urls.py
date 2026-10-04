from django.urls import path, include

from rest_framework.routers import DefaultRouter

from .views import (
    MedicineViewSet,
    AlternativeMedicineViewSet,
    process_prescription,
    get_prescription,
    patient_login,
    get_latest_prescription,
)

from .staff_views import (
    staff_login,
    staff_logout,
    staff_queue,
    staff_prescription_detail,
)



router = DefaultRouter()

router.register(
    'medicines',
    MedicineViewSet
)

router.register(
    'alternatives',
    AlternativeMedicineViewSet
)


urlpatterns = [
    path('', include(router.urls)),
    path("patients/login/", patient_login, name="patient_login"),
    path("prescriptions/process/", process_prescription, name="process_prescription"),
    path("prescriptions/<int:prescription_id>/", get_prescription, name="get_prescription"),
    path("patients/<str:token_number>/latest/", get_latest_prescription, name="get_latest_prescription"),
]

urlpatterns += [
    path("staff/login/", staff_login, name="staff_login"),
    path("staff/logout/", staff_logout, name="staff_logout"),
    path("staff/", staff_queue, name="staff_queue"),
    path("staff/prescriptions/<int:prescription_id>/", staff_prescription_detail, name="staff_prescription_detail"),
]