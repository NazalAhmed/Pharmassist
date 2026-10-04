import pandas as pd

from django.core.management.base import BaseCommand

from api.models import Medicine, AlternativeMedicine


class Command(BaseCommand):

    help = "Import medicines from medicine_substitutes.xlsx"

    def add_arguments(self, parser):
        parser.add_argument(
            "excel_file",
            type=str
        )

    def handle(self, *args, **options):

        excel_file = options["excel_file"]

        df = pd.read_excel(
            excel_file,
            sheet_name="Medicines"
        )

        for _, row in df.iterrows():

            # -----------------------------
            # Main medicine details
            # -----------------------------

            brand_name = row["BRAND NAME"]
            generic_name = row["GENERIC NAME AND DOSE"]
            dosage_form = row["DOSAGE FORM"]
            substitutes = row["SUBSTITUTES"]

            if pd.isna(brand_name):
                continue

            brand_name = str(brand_name).strip()

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

            # -----------------------------
            # Create / update main medicine
            # -----------------------------

            medicine, created = (
                Medicine.objects.update_or_create(
                    medicine_name=brand_name,
                    defaults={
                        "generic_name": generic_name,
                        "strength": "",
                        "dosage_form": dosage_form,
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

            # -----------------------------
            # Import substitutes
            # -----------------------------

            if pd.notna(substitutes):

                substitutes = str(
                    substitutes
                ).strip()

                substitute_list = substitutes.split(",")

                for substitute_name in substitute_list:

                    substitute_name = (
                        substitute_name.strip()
                    )

                    if not substitute_name:
                        continue

                    # Create substitute as Medicine
                    alternative, _ = (
                        Medicine.objects.get_or_create(
                            medicine_name=substitute_name,
                            defaults={
                                "generic_name": "",
                                "strength": "",
                                "dosage_form": "",
                                "available": False,
                            }
                        )
                    )

                    # Create relationship
                    (
                        AlternativeMedicine.objects
                        .get_or_create(
                            medicine=medicine,
                            alternative_medicine=alternative,
                            defaults={
                                "reason": "Alternative medicine"
                            }
                        )
                    )

                    self.stdout.write(
                        f"    Alternative: "
                        f"{substitute_name}"
                    )

        self.stdout.write(
            self.style.SUCCESS(
                "\nImport completed successfully!"
            )
        )