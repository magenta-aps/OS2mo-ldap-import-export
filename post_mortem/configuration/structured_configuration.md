## Use structured / typed configuration

### Recommendation

Use structured data instead of untyped dictionaries for *all* configuration.

### Symptom

The integration used to read a json(-ish) configuration file as a dictionary for part of its configuration.

Due to the lack of typing it was hard to understand exactly which settings were required/optional, their types, etc.

The validation of the resulting dictionary was also spread around the code wherever it was accessed, and was not in a standardized form.
Default values were also provided wherever the configuration was used.

On a positive note a lot of validations were in place within the integration, however a lot of the code implementing was just a poor implementation of a standard settings library.

### How

Pydantic provides a settings module in the `pydantic` package for Pydantic 1, `pydantic-settings` for Pydantic 2.

Using this module (or something similar) gives a lot of advantages over using untyped dictionaries, among others:

* Validation

Besides the type validation it is also possible to make specific validations in a standardized way.
Thus it becomes easy to determine if a configuration always upholds a given invariant.

* Default values

Having default values directly in the schema makes it clear what the default value is in a standardized way.
It also avoids having to repeat the default value throughout the program.

* Multiple configuration sources

It is possible to configure the program using whatever methodology fits better.
Sometimes and for some settings that may be environmental variables, dotenv files, json/yaml files or even CLI variables.
It is also easy to override settings programmatically in the code itself.

* Intelligent parsing of recursive configuration

Configuration can easily be a tree structure and be parsed as such in a type-safe way.

* Built-in secret management

Mixing secrets with normal configuration can be problematic, however using a settings library can help allow multiple sources to cooperate, including secret-specific sources.

* Type checking

As the schema for the configuration is established in code, it can easily be checked that no undefined settings are accessed using a type-checker.

### Current state

The integration now uses Pydantic for all the configuration.
