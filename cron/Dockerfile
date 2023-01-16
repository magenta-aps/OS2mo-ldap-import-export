FROM cethy/alpine-supercronic:v1.0
RUN apk add --no-cache curl jq
<<<<<<< HEAD
COPY ./import_all.sh /app/
RUN chmod -R 100 "/app/"
=======
COPY ./bin /app
RUN chmod -R 100 "/app"
>>>>>>> [#54292] Import all with a cronjob
ENTRYPOINT ["supercronic", "/etc/crontab"]
