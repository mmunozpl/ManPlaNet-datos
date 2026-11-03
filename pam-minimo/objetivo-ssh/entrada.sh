#!/bin/sh
# espera a la autoridad de certificados de OpenBao, guarda su clave pública
# y arranca sshd; el usuario «operador» acepta certificados con el
# principal «operador»
set -e
until curl -fsS "$OPENBAO_CA_URL" -o /etc/ssh/ca_openbao.pub 2>/dev/null \
      && [ -s /etc/ssh/ca_openbao.pub ]; do
  echo "esperando la autoridad de certificados en $OPENBAO_CA_URL"
  sleep 3
done
mkdir -p /etc/ssh/principales
echo "operador" > /etc/ssh/principales/operador
chmod 644 /etc/ssh/ca_openbao.pub /etc/ssh/principales/operador
ssh-keygen -A
exec /usr/sbin/sshd -D -e
