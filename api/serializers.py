from rest_framework import serializers
from .models import (
    Medicine,
    AlternativeMedicine,
    Prescription,
    PrescriptionMedicine,
    Patient
)


class MedicineSerializer(serializers.ModelSerializer):
    class Meta:
        model = Medicine
        fields = [
            'id',
            'medicine_name',
            'generic_name',
            'strength',
            'dosage_form',
            'available',
        ]



class AlternativeMedicineSerializer(serializers.ModelSerializer):

    alternative_name = serializers.CharField(
        source='alternative_medicine.medicine_name',
        read_only=True
    )

    alternative_available = serializers.BooleanField(
        source='alternative_medicine.available',
        read_only=True
    )

    class Meta:
        model = AlternativeMedicine
        fields = [
            'id',
            'alternative_name',
            'alternative_available',
            'reason',
        ]

class PrescriptionMedicineSerializer(serializers.ModelSerializer):
    medicine_name = serializers.CharField(
        source='medicine.medicine_name',
        read_only=True
    )

    generic_name = serializers.CharField(
        source='medicine.generic_name',
        read_only=True
    )

    available = serializers.BooleanField(
        source='medicine.available',
        read_only=True
    )

    class Meta:
        model = PrescriptionMedicine
        fields = [
            'id', 'extracted_name', 'medicine', 'medicine_name', 'generic_name',
            'dosage', 'frequency', 'duration', 'quantity',
            'confidence_score', 'available', 'pharmacist_verified',
        ]


class PatientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Patient
        fields = ['patient_id', 'name', 'phone', 'token_number']


class PrescriptionSerializer(serializers.ModelSerializer):
    medicines = PrescriptionMedicineSerializer(many=True, read_only=True)
    patient_token = serializers.CharField(source='patient.token_number', read_only=True, default='')
    patient_name = serializers.CharField(source='patient.name', read_only=True, default='')
    patient_phone = serializers.CharField(source='patient.phone', read_only=True, default='')
    patient_age = serializers.CharField(source='patient.age', read_only=True, default='')
    patient_address = serializers.CharField(source='patient.address', read_only=True, default='')

    class Meta:
        model = Prescription
        fields = [
            'id', 'source', 'prescription_file', 'extracted_text', 'status',
            'doctor_name', 'hospital_name', 'op_number', 'prescription_date', 'diagnosis',
            'patient_token', 'patient_name', 'patient_phone', 'patient_age', 'patient_address',
            'medicines', 'created_at', 'updated_at',
        ]