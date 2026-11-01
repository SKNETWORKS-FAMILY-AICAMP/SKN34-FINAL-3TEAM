# Build with repository root as context; publish with the matching learning-service revision.
FROM flyway/flyway:13.11.1-alpine
COPY backend/learning-service/src/main/resources/db/migration/ /flyway/sql/
USER 10001
ENTRYPOINT ["flyway"]
CMD ["migrate"]
