## Local development environments

### Recommendation

Ensure a fully reproducible local development environment is available.

### Symptom

The integration used to rely on a non-reproducible external Active Directory server for local development.

This meant that development could not occur effectively unless the Active Directory server was available.
It also meant that there was a limitation to the number of concurrent developers as the external resource could not be shared without coordination.

Additionally it also meant that local / CI integration tests would not be possible.

### How

Ensure that a local environment is available from the start of the project.

Evolve the development environment as the project itself develops.

If it is not possible to deploy the dependent services locally consider mocking them using WireMock or similar.

### Current state

The integration now has a local development environment using OpenLDAP in docker-compose.
