import pandas as pd

from django.core.management.base import BaseCommand

from api.models import Medicine, AlternativeMedicine


class Command(BaseCommand):

    help = "Import medicines and alternatives from Excel"

    def add_arguments(self, parser):
        parser.add_argument(
            "excel_file",
            type=str
        )

    def handle(self, *args, **options):

        excel_file = options["excel_file"]

        df = pd.read_excel(
            excel_file,
            sheet_name="Sheet1"
        )

        current_medicine = None

        for _, row in df.iterrows():

            brand_name = row["BRAND NAME"]
            generic_name = row["GENERIC NAME"]
            dosage_form = row["DOSAGE FORM"]
            availability = row["AVAILABILITY"]
            substitute = row["SUBSTITUTE"]

            # --------------------------------
            # New main medicine
            # --------------------------------

            if pd.notna(brand_name):

                brand_name = str(
                    brand_name
                ).strip()

                generic_name = (
                    str(generic_name).strip()
                    if pd.notna(generic_name)
                    else ""
                )

                dosage_form = (
                    str(dosage_form).strip()
                    if pd.notna(dosage_form)
                    else ""
                )

                available = (
                    str(availability).strip().upper()
                    == "YES"
                )

                current_medicine, created = (
                    Medicine.objects.update_or_create(
                        medicine_name=brand_name,
                        defaults={
                            "generic_name": generic_name,
                            "dosage_form": dosage_form,
                            "available": available,
                        }
                    )
                )

                if created:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Created: {brand_name}"
                        )
                    )
                else:
                    self.stdout.write(
                        f"Updated: {brand_name}"
                    )

            # --------------------------------
            # Substitute medicine
            # --------------------------------

            if (
                current_medicine
                and pd.notna(substitute)
            ):

                substitute = str(
                    substitute
                ).strip()

                if substitute:

                    # Create substitute as a Medicine
                    alternative, _ = (
                        Medicine.objects.get_or_create(
                            medicine_name=substitute,
                            defaults={
                                "generic_name": "",
                                "strength": "",
                                "dosage_form": "",
                                "available": False,
                            }
                        )
                    )

                    # Connect main medicine → alternative
                    (
                        AlternativeMedicine.objects
                        .get_or_create(
                            medicine=current_medicine,
                            alternative_medicine=alternative,
                            defaults={
                                "reason": "Alternative medicine"
                            }
                        )
                    )

                    self.stdout.write(
                        f"  Alternative: {substitute}"
                    )

        self.stdout.write(
            self.style.SUCCESS(
                "\nMedicine import completed successfully."
            )
        )