# Build with repository root as context; publish with the matching core-service revision.
FROM flyway/flyway:13.11.1-alpine
COPY backend/core-service/src/main/resources/db/migration/ /flyway/sql/
USER 10001
ENTRYPOINT ["flyway"]
CMD ["migrate"]
