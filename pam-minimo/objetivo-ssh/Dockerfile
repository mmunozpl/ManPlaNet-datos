# objetivo SSH del laboratorio: un Debian con sshd que solo acepta
# certificados firmados por la autoridad de OpenBao (sin contraseñas ni
# claves autorizadas), con un usuario «operador» para las sesiones.
# La cuenta lleva «*» como contraseña: ninguna vale, pero no está bloqueada
# (con «!», de `passwd -l`, sshd rechaza también los certificados:
# «account is locked»).
FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
        openssh-server curl ca-certificates && \
    rm -rf /var/lib/apt/lists/* && \
    mkdir -p /run/sshd && \
    useradd -m -s /bin/bash -p '*' operador
COPY sshd_config /etc/ssh/sshd_config
COPY entrada.sh /usr/local/bin/entrada.sh
RUN chmod +x /usr/local/bin/entrada.sh
EXPOSE 22
ENTRYPOINT ["/usr/local/bin/entrada.sh"]
