import re
import string

import xlsxwriter
import yaml
from fastramqpi.context import Context
from ramqp.utils import RequeueMessage

from .converters import LdapConverter
from .environments import environment
from .logging import logger
from .utils import delete_keys_from_dict


class MappingExporter(LdapConverter):
    def __init__(self, context: Context, yaml_filepath, output_filename="Mapping.xlsx"):

        context = context.copy()

        with open(yaml_filepath) as file:
            mapping = yaml.safe_load(file)

        self.user_context = context["user_context"]
        self.user_context["mapping"] = mapping
        self.settings = self.user_context["settings"]
        self.raw_mapping = self.user_context["mapping"]

        mapping = delete_keys_from_dict(
            self.raw_mapping,
            ["objectClass", "_import_to_mo_", "_export_to_ldap_"],
        )

        self.mapping = self._populate_mapping_with_templates(
            mapping,
            environment,
        )

        self.workbook = xlsxwriter.Workbook(output_filename)

        self.plain = self.workbook.add_format()
        self.plain.set_border()

        self.plain_merged = self.workbook.add_format()
        self.plain_merged.set_border()
        self.plain_merged.set_align("vcenter")
        self.plain_merged.set_align("left")

        self.bold = self.workbook.add_format({"bold": True})
        self.bold.set_border()

        # See https://www.colorhexa.com/f5d9bd for colors
        self.green_x = self.workbook.add_format()
        self.green_x.set_bg_color("#bdf5bd")
        self.green_x.set_center_across()
        self.green_x.set_border()

        self.red_x = self.workbook.add_format()
        self.red_x.set_bg_color("#f5bdbd")
        self.red_x.set_border()

        self.orange_x = self.workbook.add_format()
        self.orange_x.set_bg_color("#f5d9bd")
        self.orange_x.set_center_across()
        self.orange_x.set_border()

        self.rows_to_be_merged = 0
        self.last_json_key = None
        self.last_worksheet = None
        self.row = 1
        self.worksheets: list[xlsxwriter.worksheet] = []

    def extract_attributes_from_template(
        self, template, strings_to_split_with: list[str], more_valid_chars=""
    ):

        template = self.clean_get_current_method_from_template_string(template)

        # Valid chars in LDAP attributes
        valid_chars = string.ascii_letters + string.digits + "-" + more_valid_chars
        invalid_chars = "".join([s for s in string.punctuation if s not in valid_chars])
        invalid_chars_regex = r"[%s\s]\s*" % invalid_chars

        output = []
        for string_to_split_with in strings_to_split_with:
            if string_to_split_with in template:
                ldap_refs = template.split(string_to_split_with)[1:]

                for ldap_ref in ldap_refs:
                    ldap_attribute = re.split(invalid_chars_regex, ldap_ref)[0]
                    output.append(ldap_attribute)
        return output

    def write_headers(self, worksheet, headers: list[str]):
        """
        Write the provided headers to the excel sheet
        """
        for col, header in enumerate(headers):
            worksheet.write(0, col, header, self.bold)

    def populate_x_columns(self, row: int, json_key: str, worksheet):
        """
        Populate a row of column with crosses that indicate whether we sync or not.
        """
        try:
            if self._export_to_ldap_(json_key):
                worksheet.write(row, 3, "x", self.green_x)
            else:
                worksheet.write(row, 3, "", self.red_x)
        except RequeueMessage:
            worksheet.write(row, 3, "x", self.orange_x)

        if self._import_to_mo_(json_key, False):
            worksheet.write(row, 4, "x", self.green_x)
        else:
            worksheet.write(row, 4, "", self.red_x)

        if self._import_to_mo_(json_key, True):
            worksheet.write(row, 5, "x", self.green_x)
        else:
            worksheet.write(row, 5, "", self.red_x)

    def increment_row(self, worksheet):
        if worksheet == self.last_worksheet:
            self.row += 1
        else:
            self.row = 1
            self.last_worksheet = worksheet
            self.rows_to_be_merged = 0

    def increment_rows_to_be_merged(self, json_key):
        if json_key == self.last_json_key:
            self.rows_to_be_merged += 1
            logger.info(f"Rows to be merged: {self.rows_to_be_merged}")
        else:
            logger.info("Resetting rows to be merged")
            self.rows_to_be_merged = 1
            self.last_json_key = json_key

    def populate_row(
        self,
        worksheet,
        json_key,
        object_class,
        attribute,
        matching_attributes,
        template,
    ):

        self.increment_row(worksheet)

        logger.info(f"Populating row {self.row} with json_key = {json_key}")
        worksheet.write(self.row, 0, json_key, self.plain_merged)
        worksheet.write(self.row, 1, object_class, self.plain)
        worksheet.write(self.row, 2, attribute, self.plain)

        self.populate_x_columns(self.row, json_key, worksheet)
        worksheet.write(self.row, 6, ", ".join(set(matching_attributes)), self.plain)
        worksheet.write(self.row, 7, template, self.plain)

        self.increment_rows_to_be_merged(json_key)

    def save(self):
        for worksheet in self.worksheets:
            worksheet.autofit()
        self.workbook.close()

    def merge_rows_in_first_column(self, worksheet):
        from_row = self.row - self.rows_to_be_merged + 1
        to_row = self.row
        value = self.last_json_key
        style = self.plain_merged

        if self.rows_to_be_merged > 1:
            logger.info(f"Merging rows {from_row}-{to_row}")
            worksheet.merge_range(from_row, 0, to_row, 0, value, style)
        self.rows_to_be_merged = 1

    def add_worksheet(self, name):
        worksheet = self.workbook.add_worksheet(name)
        self.worksheets.append(worksheet)
        return worksheet

    def export_mapping(self):

        mo_split_strings = [
            "mo_employee.",
            "mo_employee_it_user.",
            "mo_employee_address.",
            "mo_org_unit_address.",
            "mo_employee_engagement.",
            "mo_holstebro_cust.",
        ]

        ldap_split_strings = ["ldap."]

        worksheet1 = self.add_worksheet("AD-to-MO")
        worksheet2 = self.add_worksheet("MO-to-AD")

        # LDAP TO MO headers
        headers_ws1 = [
            "user_key",
            "MO object class",
            "MO attribute",
            "MO-to-AD",
            "AD-to-MO",
            "AD-to-MO (manual import)",
            "AD attribute(s)",
            "template",
        ]
        self.write_headers(worksheet1, headers_ws1)

        # MO TO LDAP headers
        headers_ws2 = [
            "user_key",
            "AD object class",
            "AD attribute",
            "MO-to-AD",
            "AD-to-MO",
            "AD-to-MO (manual import)",
            "MO attribute(s)",
            "template",
        ]
        self.write_headers(worksheet2, headers_ws2)

        logger.info("Writing ldap-to-mo sheet")
        for json_key in self.get_ldap_to_mo_json_keys():
            object_class = self.find_mo_object_class(json_key).split(".")[-1]

            for mo_attribute in self.get_mo_attributes(json_key):
                template = self.raw_mapping["ldap_to_mo"][json_key][mo_attribute]
                ldap_attributes = self.extract_attributes_from_template(
                    template, ldap_split_strings
                )
                if not ldap_attributes:
                    continue

                self.populate_row(
                    worksheet1,
                    json_key,
                    object_class,
                    mo_attribute,
                    ldap_attributes,
                    template,
                )

            self.merge_rows_in_first_column(worksheet1)

        logger.info("Writing mo-to-ldap sheet")
        for json_key in self.get_mo_to_ldap_json_keys():
            object_class = self.find_ldap_object_class(json_key)

            for ldap_attribute in self.get_ldap_attributes(json_key):
                template = self.raw_mapping["mo_to_ldap"][json_key][ldap_attribute]

                mo_attributes = self.extract_attributes_from_template(
                    template, mo_split_strings, more_valid_chars="_"
                )
                if not mo_attributes:
                    logger.info("No MO Attributes found")
                    continue

                self.populate_row(
                    worksheet2,
                    json_key,
                    object_class,
                    ldap_attribute,
                    mo_attributes,
                    template,
                )

            self.merge_rows_in_first_column(worksheet2)

        self.save()
