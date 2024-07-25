## Use standard formats

### Recommendation

Use standard file formats instead of your own

### Symptom

The integration used to read a custom extended JSON file format for configuration.

The extensions were implemented to allow trailing commas in lists or dictionaries, and to allow for comments.

However implementing file formats is difficult, usually involving compiler tech, and as such it is hard to get right.

The implementation of the custom file format in the integration took the form of a regex translation, implemented with the below code:
```python
def read_mapping_json(filename: str) -> Any:
    with open(filename) as file:
        data = "\n".join(file.readlines())
        data = re.sub(r"/\*.*\*/", "", data, flags=re.DOTALL)  # Block comments
        data = re.sub(r"//[^\n]*", "", data)  # Line comments
        data = re.sub(
            r",(\s*[}\]])", "\\1", data
        )  # remove trailing commas after the last element in a list or dict
        return json.loads(data)
```
It should be clear that these rules also affect the data stores within inside keys and values.

### How

Pick the right format for your needs, and use a library to parse it.

If you need comments, pick a different format than JSON (TOML, YAML, JSON5, HJSON, etc), or write comments within the chosen format.

DIPEX infamously does comments in JSON using prefixed keys, alike: `"//": "My comment goes here"`.
The same approach is taken by the Google Firebase documentation.

Using a standard format also allows one to use the ecosystem of tools for the format.
This includes, linters, schemas, formatters, query tools, databases, etc, etc.

### Current state

The integration now uses Pydantic for all configuration allowing for multiple sources and formats.
