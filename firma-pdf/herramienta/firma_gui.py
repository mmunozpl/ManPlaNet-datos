"""Aplicación de escritorio para firmar PDF con el certificado de la FNMT.

Usa las funciones de firmar.py: elegir el certificado (uno de los instalados
en Firefox o Chrome, o un fichero .p12 o .pfx) y el documento, firmar con el
pie en todas las páginas, comprobar la firma y abrir VALIDe. La contraseña
no se guarda nunca; se recuerdan el último certificado, la última carpeta y
las opciones.

Uso:
    firma_gui.py [documento.pdf]
    firma_gui.py --comprobar documento_firmado.pdf
"""
import contextlib
import io
import subprocess
import sys
import threading
from pathlib import Path

from PySide6.QtCore import QObject, QSettings, Qt, QUrl, Signal
from PySide6.QtGui import (
    QDesktopServices, QFontDatabase, QIcon, QPixmap,
)
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))
import almacenes  # noqa: E402
import firmar as f  # noqa: E402

TITULO = "Firma de documentos - ManPla.net"
ICONO = f.RECURSOS / "recursos" / "icono.png"
# carpeta donde se buscan ficheros .p12 o .pfx
CARPETAS_CERTS = [f.CARPETA_CERTS]
TSA_DEFECTO = f.TSA_DEFECTO


class Avisador(QObject):
    """Lleva al hilo de la interfaz el resultado de una tarea."""

    hecho = Signal(str, bool, object)
    valide = Signal(object)


class DialogoCodigo(QDialog):
    """Muestra el código de seguridad de VALIDe para que lo escriba quien
    firma. El programa no lo lee: solo trae la imagen y envía lo escrito."""

    def __init__(self, padre: QWidget, sesion, fichero: str) -> None:
        super().__init__(padre)
        self.sesion = sesion
        self.setWindowTitle("Enviar a VALIDe")
        caja = QVBoxLayout(self)
        nota = QLabel(
            f"Se enviará <b>{fichero}</b> a VALIDe, la plataforma @firma de "
            "la Administración. Escribe el código de seguridad de la imagen.")
        nota.setWordWrap(True)
        caja.addWidget(nota)
        self.imagen = QLabel()
        self.imagen.setAlignment(Qt.AlignCenter)
        caja.addWidget(self.imagen)
        fila = QHBoxLayout()
        self.codigo = QLineEdit()
        self.codigo.setPlaceholderText("código de la imagen")
        otra = QPushButton("Otra imagen")
        otra.clicked.connect(self.cargar)
        fila.addWidget(self.codigo, 1)
        fila.addWidget(otra)
        caja.addLayout(fila)
        botones = QDialogButtonBox(QDialogButtonBox.Ok |
                                   QDialogButtonBox.Cancel)
        botones.button(QDialogButtonBox.Ok).setText("Enviar")
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)
        caja.addWidget(botones)
        self.cargar()

    def cargar(self) -> None:
        """Trae una imagen nueva del código, ampliada al doble."""
        px = QPixmap()
        px.loadFromData(self.sesion.captcha())
        self.imagen.setPixmap(px.scaled(px.width() * 2, px.height() * 2,
                                        Qt.KeepAspectRatio,
                                        Qt.SmoothTransformation))
        self.codigo.clear()
        self.codigo.setFocus()

class Ventana(QWidget):
    """Ventana principal."""

    def __init__(self, documento: str | None = None) -> None:
        super().__init__()
        self.setWindowTitle(TITULO)
        self.setWindowIcon(QIcon(str(ICONO)))
        self.setAcceptDrops(True)
        self.ajustes = QSettings("ManPla", "firma-pdf")
        self.avisador = Avisador()
        self.avisador.hecho.connect(self._fin_tarea)
        self.avisador.valide.connect(self._respuesta_valide)
        self.sesion_valide = None
        self.datos_cert = None
        self._construir()
        self._cargar_certificados()
        if documento:
            self._poner_documento(documento)

    # construcción ---------------------------------------------------------

    def _construir(self) -> None:
        """Monta los tres bloques, los botones y el registro."""
        raiz = QVBoxLayout(self)

        raiz.addWidget(self._bloque_certificado())

        # documento
        caja_d = QGroupBox("2. Documento (también se puede arrastrar)")
        fd = QFormLayout(caja_d)
        fila = QHBoxLayout()
        self.doc = QLineEdit()
        self.doc.textChanged.connect(self._doc_cambiado)
        b_doc = QPushButton("Elegir…")
        b_doc.clicked.connect(self._elegir_doc)
        fila.addWidget(self.doc, 1)
        fila.addWidget(b_doc)
        fd.addRow("PDF", fila)
        fila = QHBoxLayout()
        self.salida = QLineEdit()
        b_sal = QPushButton("Cambiar…")
        b_sal.clicked.connect(self._elegir_salida)
        fila.addWidget(self.salida, 1)
        fila.addWidget(b_sal)
        fd.addRow("Firmado", fila)
        raiz.addWidget(caja_d)

        # opciones
        caja_o = QGroupBox("3. Opciones")
        fo = QFormLayout(caja_o)
        # opcionales: vacíos, enseñan una sugerencia en gris que no se usa
        # como valor; sin dato, la celda del pie va vacía
        self.motivo = QLineEdit(self.ajustes.value("motivo", ""))
        self.motivo.setPlaceholderText(
            "opcional: conformidad con la propuesta, aprobación del informe")
        self.lugar = QLineEdit(self.ajustes.value("lugar", ""))
        self.lugar.setPlaceholderText("opcional: ciudad y país")
        fo.addRow("Motivo", self.motivo)
        fo.addRow("Lugar", self.lugar)
        # la referencia es de cada documento: no se recuerda
        self.referencia = QLineEdit()
        self.referencia.setPlaceholderText(
            "opcional: propuesta, expediente, contrato")
        fo.addRow("Referencia", self.referencia)
        fila = QHBoxLayout()
        self.con_tsa = QCheckBox("Sello de tiempo")
        self.con_tsa.setChecked(
            self.ajustes.value("con_tsa", "false") == "true")
        tsa = self.ajustes.value("tsa", TSA_DEFECTO)
        # freetsa.org no la admite @firma: se cambia por la cualificada
        if "freetsa.org" in tsa:
            tsa = TSA_DEFECTO
        self.tsa = QLineEdit(tsa)
        self.tsa.setPlaceholderText(
            f"dirección del servicio de sellado, p. ej. {TSA_DEFECTO}")
        fila.addWidget(self.con_tsa)
        fila.addWidget(self.tsa, 1)
        fo.addRow("", fila)
        self.reducir = QCheckBox(
            "Reducir el contenido para dejar sitio al pie")
        self.reducir.setChecked(
            self.ajustes.value("reducir", "true") == "true")
        fo.addRow("", self.reducir)
        raiz.addWidget(caja_o)

        # botones
        fila = QHBoxLayout()
        self.b_firmar = QPushButton("Firmar")
        self.b_firmar.setDefault(True)
        self.b_firmar.clicked.connect(self._firmar)
        self.b_comprobar = QPushButton("Comprobar firma")
        self.b_comprobar.clicked.connect(self._comprobar)
        b_valide = QPushButton("Enviar a VALIDe")
        b_valide.setToolTip("Envía el firmado a VALIDe y muestra su "
                            "respuesta (el código lo escribes tú)")
        b_valide.clicked.connect(self._valide)
        b_ver = QPushButton("Abrir firmado")
        b_ver.clicked.connect(lambda: self._abrir(self.salida.text()))
        for b in (self.b_firmar, self.b_comprobar, b_valide, b_ver):
            fila.addWidget(b)
        raiz.addLayout(fila)

        # registro de lo hecho
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        self.log.setMinimumHeight(190)
        raiz.addWidget(self.log, 1)
        self.resize(720, 680)

    def _bloque_certificado(self) -> QGroupBox:
        """Elección del certificado: instalados, ficheros y contraseña.

        Lo reutiliza la ventana de firma múltiple.
        """
        caja_c = QGroupBox("1. Certificado")
        fc = QFormLayout(caja_c)
        fila = QHBoxLayout()
        self.combo_cert = QComboBox()
        self.combo_cert.setMinimumWidth(380)
        self.combo_cert.currentIndexChanged.connect(self._cert_cambiado)
        b_recargar = QPushButton("Recargar")
        b_recargar.setToolTip("Vuelve a leer los certificados instalados")
        b_recargar.clicked.connect(self._cargar_certificados)
        b_cert = QPushButton("Fichero…")
        b_cert.setToolTip("Añade un certificado .p12 o .pfx")
        b_cert.clicked.connect(self._elegir_cert)
        fila.addWidget(self.combo_cert, 1)
        fila.addWidget(b_recargar)
        fila.addWidget(b_cert)
        fc.addRow("Certificado", fila)
        fila = QHBoxLayout()
        self.clave = QLineEdit()
        self.clave.setEchoMode(QLineEdit.Password)
        self.clave.returnPressed.connect(self._abrir_cert)
        self.b_abrir = QPushButton("Abrir")
        self.b_abrir.clicked.connect(self._abrir_cert)
        fila.addWidget(self.clave, 1)
        fila.addWidget(self.b_abrir)
        self.rot_clave = QLabel("Contraseña")
        fc.addRow(self.rot_clave, fila)
        self.info_cert = QLabel("Certificado sin abrir")
        self.info_cert.setWordWrap(True)
        fc.addRow("", self.info_cert)
        return caja_c

    # certificado ----------------------------------------------------------

    def _cargar_certificados(self) -> None:
        """Llena la lista: primero los instalados, después los ficheros."""
        elementos = []
        try:
            for c in almacenes.listar():
                c["caduca"] = c["caduca"].astimezone(f.ZONA)
                etiqueta = (f"{c['nombre']} · caduca {c['caduca']:%d/%m/%Y}"
                            f" · {c['almacen']}")
                elementos.append((etiqueta,
                                  dict(c, clave_id="inst:" + c["huella"])))
        except (OSError, ValueError, subprocess.SubprocessError) as e:
            # sin la herramienta del sistema solo quedan los ficheros
            self._escribir(f"no se pudieron leer los certificados "
                           f"instalados ({e}); quedan los ficheros")
        rutas = [str(p) for carpeta in CARPETAS_CERTS if carpeta.is_dir()
                 for p in sorted(carpeta.glob("*"))
                 if p.suffix.lower() in (".p12", ".pfx")]
        for r in self.ajustes.value("certs", []) or []:
            if r not in rutas and Path(r).exists():
                rutas.append(r)
        for r in rutas:
            elementos.append((f"Fichero: {Path(r).name}",
                              {"tipo": "p12", "ruta": r, "clave_id": r}))
        self.combo_cert.blockSignals(True)
        self.combo_cert.clear()
        for etiqueta, dato in elementos:
            self.combo_cert.addItem(etiqueta, dato)
        ultimo = self.ajustes.value("ultimo_cert", "")
        i = next((k for k, (_, d) in enumerate(elementos)
                  if d["clave_id"] == ultimo), 0)
        self.combo_cert.setCurrentIndex(i)
        self.combo_cert.blockSignals(False)
        self._cert_cambiado()

    def _elegir_cert(self) -> None:
        """Añade un certificado desde el diálogo de ficheros."""
        r, _ = QFileDialog.getOpenFileName(
            self, "Certificado", str(Path.home()),
            "Certificados (*.p12 *.pfx)")
        if r:
            self._recordar_cert(r)

    def _recordar_cert(self, ruta: str) -> None:
        """Guarda la ruta entre los certificados recordados y la elige."""
        certs = list(self.ajustes.value("certs", []) or [])
        if ruta not in certs:
            certs.append(ruta)
        self.ajustes.setValue("certs", certs)
        self.ajustes.setValue("ultimo_cert", ruta)
        self._cargar_certificados()

    def _cert_cambiado(self) -> None:
        """Ajusta la contraseña y los datos al certificado elegido.

        De un certificado instalado ya se conoce la parte pública, así que
        sus datos se muestran sin contraseña; la clave se lee al firmar. Un
        fichero, en cambio, va cifrado y hay que abrirlo antes.
        """
        self.datos_cert = None
        self.clave.clear()
        dato = self.combo_cert.currentData()
        if not dato:
            self.info_cert.setText("Sin certificados: añade un fichero")
            return
        self.ajustes.setValue("ultimo_cert", dato["clave_id"])
        if dato["tipo"] != "p12":
            # instalado en el sistema: Windows y macOS piden permiso por su
            # cuenta; en Linux hace falta la contraseña principal
            self.rot_clave.setText(dato["rotulo_clave"])
            self.clave.setPlaceholderText(dato["ayuda_clave"]
                                          + " (no se guarda)")
            self.clave.setEnabled(dato["pide_clave"])
            self.b_abrir.setVisible(False)
            self._mostrar_cert(dato)
        else:
            self.rot_clave.setText("Contraseña")
            self.clave.setPlaceholderText("la del fichero (no se guarda)")
            self.clave.setEnabled(True)
            self.b_abrir.setVisible(True)
            self.info_cert.setText("Fichero sin abrir: escribe su contraseña")

    def _abrir_cert(self) -> None:
        """Abre un fichero de certificado con su contraseña."""
        dato = self.combo_cert.currentData()
        if not dato or dato["tipo"] != "p12":
            return
        try:
            d = f.datos_certificado(Path(dato["ruta"]),
                                    self.clave.text().encode())
        except Exception:
            self.datos_cert = None
            self.info_cert.setText("<b style='color:#b00'>No se pudo abrir: "
                                   "¿contraseña?</b>")
            return
        self._mostrar_cert(d)

    def _mostrar_cert(self, d: dict) -> None:
        """Muestra titular, emisor y caducidad con su color."""
        self.datos_cert = d
        dias = (d["caduca"] - f.dt.datetime.now(f.ZONA)).days
        color = "#b00" if dias < 0 else ("#b60" if dias < 30 else "#070")
        estado = ("caducado" if dias < 0 else f"quedan {dias} días")
        self.info_cert.setText(
            f"<b>{d['nombre']}</b> · emitido por {d['emisor']} · "
            f"<span style='color:{color}'>caduca el "
            f"{d['caduca']:%d/%m/%Y} ({estado})</span>")

    # documento ------------------------------------------------------------

    def _elegir_doc(self) -> None:
        """Elige el PDF que se va a firmar."""
        r, _ = QFileDialog.getOpenFileName(
            self, "Documento", self.ajustes.value("carpeta", str(Path.home())),
            "PDF (*.pdf)")
        if r:
            self._poner_documento(r)

    def _poner_documento(self, ruta: str) -> None:
        """Pone el documento y recuerda su carpeta."""
        self.doc.setText(ruta)
        self.ajustes.setValue("carpeta", str(Path(ruta).parent))

    def _doc_cambiado(self, texto: str) -> None:
        """Propone el nombre del firmado junto al original."""
        p = Path(texto)
        if p.suffix.lower() == ".pdf":
            self.salida.setText(str(p.with_name(p.stem + "_firmado.pdf")))

    def _elegir_salida(self) -> None:
        """Cambia dónde se guarda el firmado."""
        r, _ = QFileDialog.getSaveFileName(
            self, "Guardar firmado como", self.salida.text(), "PDF (*.pdf)")
        if r:
            self.salida.setText(r)

    def dragEnterEvent(self, ev) -> None:  # noqa: N802
        """Acepta PDF y certificados arrastrados."""
        if ev.mimeData().hasUrls():
            ev.acceptProposedAction()

    def dropEvent(self, ev) -> None:  # noqa: N802
        """Un PDF va al documento; un .p12 o .pfx, a los certificados."""
        for url in ev.mimeData().urls():
            r = url.toLocalFile()
            if r.lower().endswith(".pdf"):
                self._poner_documento(r)
            elif r.lower().endswith((".p12", ".pfx")):
                self._recordar_cert(r)

    # acciones -------------------------------------------------------------

    def _firmar(self) -> None:
        """Comprueba lo necesario y firma en segundo plano."""
        if not self.datos_cert:
            self._abrir_cert()
            if not self.datos_cert:
                return
        entrada, salida = Path(self.doc.text()), Path(self.salida.text())
        if not entrada.is_file():
            return self._aviso("Elige el documento que vas a firmar.")
        if entrada.resolve() == salida.resolve():
            return self._aviso("El firmado no puede sobrescribir el original.")
        if salida.exists() and QMessageBox.question(
                self, "Firma", f"{salida.name} ya existe. ¿Sustituirlo?"
        ) != QMessageBox.Yes:
            return
        self._guardar_opciones()
        # con la casilla marcada y la dirección vacía, el servicio cualificado
        tsa = ((self.tsa.text().strip() or TSA_DEFECTO)
               if self.con_tsa.isChecked() else None)
        dato = self.combo_cert.currentData()
        clave = self.clave.text()
        opciones = (self.motivo.text(), self.lugar.text(), tsa,
                    self.reducir.isChecked(), self.referencia.text().strip())
        self._escribir(f"firmando {entrada.name} como "
                       f"{self.datos_cert['nombre']}…")
        self._en_marcha(True)

        def trabajo():
            try:
                if dato["tipo"] != "p12":
                    # la clave sale del almacén a memoria, nunca a disco
                    p12, cl = almacenes.exportar(dato, clave)
                else:
                    p12, cl = Path(dato["ruta"]), clave.encode()
                r = f.firmar_documento(entrada, salida, p12, cl, *opciones)
                msg = (f"firmado: {r['salida']}\n  id {r['id']}, "
                       f"{r['paginas']} páginas"
                       + (", con sello de tiempo" if tsa else ""))
                self.avisador.hecho.emit(msg, True, r["salida"])
            except Exception as e:  # se muestra al usuario
                self.avisador.hecho.emit(f"error al firmar: {e}", False, None)

        threading.Thread(target=trabajo, daemon=True).start()

    def _comprobar(self) -> None:
        """Valida el firmado (o el documento elegido) en segundo plano."""
        destino = Path(self.salida.text())
        if not destino.is_file():
            destino = Path(self.doc.text())
        if not destino.is_file():
            r, _ = QFileDialog.getOpenFileName(
                self, "PDF firmado", self.ajustes.value("carpeta", ""),
                "PDF (*.pdf)")
            if not r:
                return
            destino = Path(r)
        self._escribir(f"comprobando {destino.name} (consulta OCSP)…")
        self._en_marcha(True)

        def trabajo():
            buf = io.StringIO()
            try:
                with contextlib.redirect_stdout(buf):
                    ok = f.comprobar(destino, "hard-fail")
                self.avisador.hecho.emit(buf.getvalue().rstrip(), ok, None)
            except Exception as e:
                self.avisador.hecho.emit(
                    buf.getvalue() + f"error al comprobar: {e}", False, None)

        threading.Thread(target=trabajo, daemon=True).start()

    def _valide(self) -> None:
        """Envía el firmado a VALIDe con el código que escribe la persona."""
        destino = Path(self.salida.text())
        if not destino.is_file():
            destino = Path(self.doc.text())
        if not destino.is_file():
            return self._aviso("No hay documento firmado que enviar.")
        self._destino_valide = destino
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.sesion_valide = f.SesionValide()
        except Exception as e:
            return self._aviso(f"VALIDe no responde: {e}")
        finally:
            QApplication.restoreOverrideCursor()
        self._pedir_codigo()

    def _pedir_codigo(self) -> None:
        """Abre el diálogo del código y envía en segundo plano."""
        destino, sesion = self._destino_valide, self.sesion_valide
        try:
            dlg = DialogoCodigo(self, sesion, destino.name)
        except Exception as e:
            return self._aviso(f"VALIDe no responde: {e}")
        if dlg.exec() != QDialog.Accepted or not dlg.codigo.text().strip():
            return
        codigo = dlg.codigo.text()
        self._escribir(f"enviando {destino.name} a VALIDe…")
        self._en_marcha(True)

        def trabajo():
            try:
                r = sesion.enviar(destino, codigo)
            except Exception as e:
                r = {"estado": "error", "texto": f"error de red: {e}",
                     "pagina": None}
            self.avisador.valide.emit(r)

        threading.Thread(target=trabajo, daemon=True).start()

    def _respuesta_valide(self, r: dict) -> None:
        """Muestra la respuesta de VALIDe o pide otro código."""
        self._en_marcha(False)
        if r["estado"] == "codigo_incorrecto":
            self._escribir("VALIDe: código incorrecto, otra imagen")
            return self._pedir_codigo()
        self._escribir("VALIDe responde:\n" + r["texto"])
        if r["pagina"] and QMessageBox.question(
                self, "VALIDe", "¿Abrir la respuesta completa en el "
                "navegador?") == QMessageBox.Yes:
            self._abrir(str(r["pagina"]))

    def _fin_tarea(self, mensaje: str, ok: bool, _r: object) -> None:
        """Recibe el resultado del hilo de trabajo."""
        self._en_marcha(False)
        self._escribir(mensaje)
        if not ok and mensaje.startswith("error"):
            self._aviso(mensaje)

    # utilidades -----------------------------------------------------------

    def _guardar_opciones(self) -> None:
        """Recuerda las opciones, nunca la contraseña."""
        self.ajustes.setValue("motivo", self.motivo.text())
        self.ajustes.setValue("lugar", self.lugar.text())
        self.ajustes.setValue("tsa", self.tsa.text())
        self.ajustes.setValue("con_tsa", str(self.con_tsa.isChecked()).lower())
        self.ajustes.setValue("reducir",
                              str(self.reducir.isChecked()).lower())

    def _en_marcha(self, si: bool) -> None:
        """Bloquea los botones mientras corre una tarea."""
        for b in (self.b_firmar, self.b_comprobar):
            b.setEnabled(not si)
        QApplication.setOverrideCursor(Qt.WaitCursor) if si else \
            QApplication.restoreOverrideCursor()

    def _escribir(self, texto: str) -> None:
        """Añade una entrada al registro de la ventana."""
        self.log.appendPlainText(texto + "\n")

    def _aviso(self, texto: str) -> None:
        """Muestra un aviso modal."""
        QMessageBox.warning(self, "Firma", texto)

    @staticmethod
    def _abrir(ruta: str) -> None:
        """Abre un fichero con la aplicación por defecto del sistema."""
        if ruta and Path(ruta).exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(ruta))


def main() -> None:
    """Arranca la aplicación (o comprueba un PDF sin ventana)."""
    if len(sys.argv) == 2 and sys.argv[1] == "--autoprueba":
        sys.exit(f.autoprueba())
    if len(sys.argv) == 3 and sys.argv[1] == "--comprobar":
        sys.exit(0 if f.comprobar(Path(sys.argv[2]), "hard-fail") else 1)
    app = QApplication(sys.argv)
    app.setApplicationName(TITULO)
    app.setDesktopFileName("firma-pdf")
    app.setWindowIcon(QIcon(str(ICONO)))
    v = Ventana(sys.argv[1] if len(sys.argv) > 1 else None)
    v.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
