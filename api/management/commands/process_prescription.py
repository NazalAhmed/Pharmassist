from django.core.management.base import BaseCommand

from api.models import Prescription
from api.services import process_prescription_full


class Command(BaseCommand):

    help = "Run OCR and medicine extraction on a prescription"

    def add_arguments(self, parser):
        parser.add_argument("prescription_id", type=int)

    def handle(self, *args, **options):

        prescription_id = options["prescription_id"]

        try:
            prescription = Prescription.objects.get(id=prescription_id)
        except Prescription.DoesNotExist:
            self.stdout.write(self.style.ERROR("Prescription not found."))
            return

        self.stdout.write("Processing prescription...")

        prescription = process_prescription_full(prescription)

        if prescription.status == "failed":
            self.stdout.write(self.style.ERROR("OCR/Extraction failed."))
            return

        self.stdout.write(self.style.SUCCESS("\nOCR completed!\n"))
        self.stdout.write("==============================")
        self.stdout.write("\nEXTRACTED MEDICINES\n")

        for item in prescription.medicines.all():

            self.stdout.write(f"\nMedicine: {item.extracted_name}")
            self.stdout.write(f"Dosage: {item.dosage}")
            self.stdout.write(f"Frequency: {item.frequency}")
            self.stdout.write(f"Duration: {item.duration}")
            self.stdout.write(f"Matched: {item.medicine}")
            self.stdout.write(f"Confidence: {item.confidence_score:.1f}%")

        self.stdout.write("\n==============================")