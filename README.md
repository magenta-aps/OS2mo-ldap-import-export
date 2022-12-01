### Running the tests

You use `poetry` and `pytest` to run the tests:

`poetry run pytest -s`

You can also run specific files

`poetry run pytest tests/<test_folder>/<test_file.py>`

and even use filtering with `-k`

`poetry run pytest -k "Manager"`

You can use the flags `-vx` where `v` prints the test & `x` makes the test stop if any tests fails (Verbose, X-fail)

You can get the coverage report like this:

`poetry run pytest -s --cov --cov-report term-missing -vv`

### Using the app

First create a `docker-compose.override.yml` file based on the
`docker-compose.override.template.yml` file

You can then boot the app like this:

```
poetry lock
poetry install
docker-compose up
```

You can use the app like this:

```
import requests
r = requests.get("http://0.0.0.0:8000/LDAP/all")
print(r.json()[-2])
```

Or you can go to [the swagger documentation](http://localhost:8000/docs) for a more graphic interface

### Setting up conversion file

The conversion file specifies in json how to map attributes from MO to LDAP and from LDAP to MO,
and takes the form:

```
{
  "ldap_to_mo":
    "Employee": {
      "objectClass": "ramodels.mo.employee.Employee",
      [other attributes]
    },
    [other classes]
  },
  "mo_to_ldap":
    "Employee": {
      "objectClass": "user",
      [other attributes]
    },
    [other classes]
  }
}
    
```
Here the "Employee" class is specified to take the class "ramodels.mo.employee.Employee" when creating or 
updating a MO object, and to take the class "user" when creating or updating an LDAP object. 
If the LDAP schema uses a different name for the employee object type, specify that class here.

Other valid classes include "Email" and "Postadresse";
any MO class with a corresponding implementation in `main.py` should be acceptable.

Each class _must_ specify:
* An "objectClass" attribute
* An attribute that corresponds to the primary key name for the MO or LDAP class
* Attributes for all required fields in the MO or LDAP class to be written

Values in the json structure may be normal strings, or a string containing one or more jinja2 templates,
to be used for extracting values. For example:

```
  [...]
  "mo_to_ldap": {
    "Employee": {
      "objectClass": "user",
      "employeeID": "{{mo_employee.cpr_no}}",
    }
  }
  [...]
```
Here, `employeeID` in the resulting LDAP object will be set to the `cpr_no` value from the MO object.
The `mo_employee` object will be added to the template context by adding to the `mo_object_dict` in 
`mo_import_export.main.listen_to_changes_in_employees`.

More advanced template string may be constructed, such as:
```
  [...]
  "ldap_to_mo": {
    "Employee": {
      "objectClass": "user",
      "givenname": "{{ldap.givenName or ldap.name|splitlast|first}}",
    }
  }
  [...]
```
Here, the MO object's `givenname` attribute will be set to the givenName attribute from LDAP,
if it exists, or if it does not, to the name attribute modified to be split by the last space and 
using the first part of the result.

In addition to the [Jinja2's builtin filters](https://jinja.palletsprojects.com/en/3.1.x/templates/#builtin-filters),
the following filters are available:

* `splitfirst`: Splits a string at the first space, returning two elements
  This is convenient for splitting a name into a givenName and a surname
  and works for names with no spaces (surname will then be empty)
* `splitlast`: Splits a string at the last space, returning two elements
  This is convenient for splitting a name into a givenName and a surname
  and works for names with no spaces (givenname will then be empty)
* `strftime`: Accepts a datetime object and formats it as a string

In addition to filters, a few methods have been made available for the templates.
These are called using the normal function call syntax:
```
{
  "key": "{{ nonejoin(ldap.postalCode, ldap.streetAddress) }}"
}
```
* `nonejoin`: Joins two or more strings together with comma, omitting any Falsy values 
  (`None`, `""`, `0`, `False`, `{}` or `[]`)

Note: dette kan godt implementeres med et almindeligt filter
