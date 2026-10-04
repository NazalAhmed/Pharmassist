from django.shortcuts import render
from django.db.models import Q

from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import action, api_view


from .models import Medicine, Prescription, AlternativeMedicine, Patient
from .serializers import MedicineSerializer, PrescriptionSerializer, AlternativeMedicineSerializer, PatientSerializer

from .services import process_prescription_full

# Create your views here.

class MedicineViewSet(viewsets.ModelViewSet):

    queryset = Medicine.objects.all()
    serializer_class = MedicineSerializer


    @action(
        detail=False,
        methods=['get']
    )
    def search(self, request):

        query = request.query_params.get(
            'q',
            ''
        )

        medicines = Medicine.objects.filter(
            Q(medicine_name__icontains=query) |
            Q(generic_name__icontains=query)
        )

        serializer = self.get_serializer(
            medicines,
            many=True
        )

        return Response(
            serializer.data
        )

class PrescriptionUploadView(APIView):

    def post(self, request):

        serializer = PrescriptionSerializer(
            data=request.data
        )

        if serializer.is_valid():

            prescription = serializer.save(
                status="uploaded"
            )

            return Response(
                PrescriptionSerializer(
                    prescription
                ).data,
                status=status.HTTP_201_CREATED
            )

        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )

class AlternativeMedicineViewSet(viewsets.ReadOnlyModelViewSet):

    queryset = AlternativeMedicine.objects.all()

    serializer_class = AlternativeMedicineSerializer


@api_view(["GET"])
def get_prescription(request, prescription_id):

    try:
        prescription = Prescription.objects.get(
            id=prescription_id
        )
    except Prescription.DoesNotExist:
        return Response(
            {"error": "Prescription not found"},
            status=status.HTTP_404_NOT_FOUND
        )

    medicines = []

    for item in prescription.medicines.all():

        medicines.append({
            "id": item.id,
            "medicine": item.extracted_name,
            "dosage": item.dosage,
            "frequency": item.frequency,
            "duration": item.duration,
            "confidence": item.confidence_score,
            "verified": item.pharmacist_verified,
        })

    patient = None

    if prescription.patient:
        patient = {
            "id": prescription.patient.patient_id,
            "name": prescription.patient.name,
        }

    return Response({
        "id": prescription.id,
        "status": prescription.status,
        "patient": patient,
        "prescription_file": prescription.prescription_file.url,
        "medicines": medicines,
        "created_at": prescription.created_at,
    })



@api_view(["POST"])
def patient_login(request):
    """
    'Login' with just a phone number. Creates the Patient on first
    use and always returns their (stable) token number.
    """

    phone = request.data.get("phone")

    if not phone:
        return Response(
            {"error": "Phone number is required"},
            status=status.HTTP_400_BAD_REQUEST
        )

    patient, _ = Patient.objects.get_or_create(
        phone=phone,
        defaults={
            "name": "",
            "patient_id": f"P{Patient.objects.count() + 1:06d}",
        }
    )

    return Response(PatientSerializer(patient).data)


@api_view(["POST"])
def process_prescription(request):

    prescription_file = request.FILES.get("prescription_file")
    token_number = request.data.get("token_number")

    if not prescription_file:
        return Response(
            {"error": "No prescription image uploaded"},
            status=status.HTTP_400_BAD_REQUEST
        )

    if not token_number:
        return Response(
            {"error": "token_number is required - log in with your phone number first"},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        patient = Patient.objects.get(token_number=token_number)
    except Patient.DoesNotExist:
        return Response(
            {"error": "Invalid token - please log in again"},
            status=status.HTTP_404_NOT_FOUND
        )

    prescription = Prescription.objects.create(
        prescription_file=prescription_file,
        source="patient",
        status="uploaded",
        patient=patient,
    )

    process_prescription_full(prescription)

    return Response(PrescriptionSerializer(prescription).data, status=status.HTTP_201_CREATED)


@api_view(["GET"])
def get_latest_prescription(request, token_number):
    """
    The app polls this to see if the patient's most recent
    prescription has been marked ready by the pharmacist.
    """

    try:
        patient = Patient.objects.get(token_number=token_number)
    except Patient.DoesNotExist:
        return Response({"error": "Invalid token"}, status=status.HTTP_404_NOT_FOUND)

    prescription = patient.prescriptions.order_by("-created_at").first()

    if not prescription:
        return Response({"error": "No prescriptions found for this token"}, status=status.HTTP_404_NOT_FOUND)

    return Response(PrescriptionSerializer(prescription).data)