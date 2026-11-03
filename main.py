import os
import sqlite3
from datetime import datetime, timedelta
os.environ['KIVY_WINDOW'] = 'sdl2'
os.environ['KIVY_IMAGE'] = 'sdl2'

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.lang import Builder
from kivy.utils import platform

Builder.load_file(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'main.kv'))

class CalculadorScreen(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Evita recalcular mientras se establecen los tres selectores de fecha.
        self._inicializando_fecha = True
        # En Android, guardar en el espacio privado persistente de la app.
        # En PC, conservar el comportamiento original: usar la carpeta de trabajo
        # desde la que se ejecuta main.py, para no perder acceso a la base existente.
        app = App.get_running_app()
        if platform == "android" and app is not None:
            carpeta_datos = app.user_data_dir
        else:
            carpeta_datos = os.getcwd()
        os.makedirs(carpeta_datos, exist_ok=True)
        ruta_db = os.path.join(carpeta_datos, "acumulados_azar.db")
        self.conexion = sqlite3.connect(ruta_db)
        self.cursor = self.conexion.cursor()
        
        # Tabla de ventas crudas por fecha exacta
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS ventas_acumuladas (
                fecha TEXT,
                juego TEXT,
                monto REAL,
                PRIMARY KEY (fecha, juego)
            )
        """)
        
        # Tabla general de comisiones cerradas por día
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS comisiones_diarias (
                fecha TEXT PRIMARY KEY,
                total_vendido REAL,
                total_comision REAL,
                total_rendir REAL
            )
        """)
        self.conexion.commit()
        
        # VARIABLES GLOBALES EN MEMORIA (Para arrastrar el Viernes al Sábado)
        self.total_rendir_viernes = 0.0
        
        self.venta_juegos_hoy = 0.0
        self.comision_juegos_hoy = 0.0
        self.rendir_juegos_hoy = 0.0
        
        self.quini_arrastrado = 0.0
        self.loto_arrastrado = 0.0
        self.telekino_arrastrado = 0.0

        # Al iniciar, seleccionar el día posterior a la última fecha guardada
        # en ventas_acumuladas. Si no hay datos, usar la fecha actual.
        self.establecer_fecha_predeterminada()
        self._inicializando_fecha = False
        self.on_fecha_cambiada()

    def establecer_fecha_predeterminada(self):
        """Selecciona el día siguiente a la fecha más reciente de ventas_acumuladas."""
        self.cursor.execute("SELECT MAX(fecha) FROM ventas_acumuladas")
        resultado = self.cursor.fetchone()
        ultima_fecha = resultado[0] if resultado else None

        if ultima_fecha:
            try:
                fecha_predeterminada = datetime.strptime(
                    ultima_fecha, "%Y-%m-%d"
                ).date() + timedelta(days=1)
            except (TypeError, ValueError):
                # Si hubiera una fecha antigua con formato inválido, no impedir
                # que se abra la pantalla.
                fecha_predeterminada = datetime.now().date()
        else:
            fecha_predeterminada = datetime.now().date()

        # Los domingos no se trabaja: si la fecha siguiente cae domingo,
        # avanzar al lunes. Esto también aplica si la tabla está vacía y hoy es domingo.
        while fecha_predeterminada.weekday() == 6:
            fecha_predeterminada += timedelta(days=1)

        anio = fecha_predeterminada.year
        self.ids.spin_anio.values = [str(y) for y in range(anio - 5, anio + 6)]
        self.ids.spin_anio.text = str(anio)
        self.ids.spin_mes.text = f"{fecha_predeterminada.month:02d}"
        self.ids.spin_dia.text = f"{fecha_predeterminada.day:02d}"

    def get_fecha_seleccionada(self):
        return f"{self.ids.spin_anio.text}-{self.ids.spin_mes.text}-{self.ids.spin_dia.text}"

    def on_fecha_cambiada(self):
        # Durante la inicialización, los selectores pueden emitir on_text varias veces.
        if getattr(self, "_inicializando_fecha", True):
            return

        fecha_sel = self.get_fecha_seleccionada()
        try:
            fecha_dt = datetime.strptime(fecha_sel, "%Y-%m-%d")
        except ValueError:
            # No romper la aplicación si el usuario pasa momentáneamente por
            # una combinación de día/mes que no existe (por ejemplo, 31 de febrero).
            self.quini_arrastrado = 0.0
            self.loto_arrastrado = 0.0
            self.telekino_arrastrado = 0.0
            self.ids.lbl_arrastre_info.text = "Seleccioná una fecha válida para calcular los arrastres."
            self.ids.lbl_historial_dia.text = "Fecha inválida. Revisá día, mes y año."
            self.ids.lbl_historial_dia.color = (1, 0.3, 0.3, 1)
            self.calcular_totales()
            return

        dia_semana = fecha_dt.weekday() # 0=Lunes, 1=Martes, 2=Miércoles, 3=Jueves, 4=Viernes, 5=Sábado
        
        self.quini_arrastrado = 0.0
        self.loto_arrastrado = 0.0
        self.telekino_arrastrado = 0.0
        
        # A. SI HOY ES MIÉRCOLES (2): Sumar lo acumulado de Lunes y Martes de esta misma semana
        if dia_semana == 2:
            lunes = (fecha_dt - timedelta(days=2)).strftime("%Y-%m-%d")
            martes = (fecha_dt - timedelta(days=1)).strftime("%Y-%m-%d")
            self.acumular_juegos_por_fechas([lunes, martes])
            
        # B. SI HOY ES SÁBADO (5): Sumar Quini/Loto de Jueves y Viernes + Telekino de toda la semana de trabajo
        elif dia_semana == 5:
            jueves = (fecha_dt - timedelta(days=2)).strftime("%Y-%m-%d")
            viernes = (fecha_dt - timedelta(days=1)).strftime("%Y-%m-%d")
            self.acumular_juegos_por_fechas([jueves, viernes])
            
            # Bolsa de Telekino de toda la semana de trabajo (Lunes a Viernes)
            fechas_tk = [(fecha_dt - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(1, 6)]
            for f in fechas_tk:
                self.cursor.execute("SELECT monto FROM ventas_acumuladas WHERE fecha = ? AND juego = 'Telekino'", (f,))
                r_tk = self.cursor.fetchone()
                if r_tk and r_tk[0]: 
                    self.telekino_arrastrado += r_tk[0]
                
        # Mostrar los arrastres calculados en el cartel naranja
        total_acumulado_mostrado = self.quini_arrastrado + self.loto_arrastrado + self.telekino_arrastrado
        if dia_semana == 5 and self.total_rendir_viernes > 0:
            self.ids.lbl_arrastre_info.text = f"Arrastres + Caja Viernes ($ {self.total_rendir_viernes:,.2f}) -> Total: ${total_acumulado_mostrado + self.total_rendir_viernes:,.2f}"
        else:
            self.ids.lbl_arrastre_info.text = f"Arrastres liquidados hoy -> Quini: ${self.quini_arrastrado:,.2f} | Loto: ${self.loto_arrastrado:,.2f} | Telekino: ${self.telekino_arrastrado:,.2f}"

        # Historial de control de caja del día
        self.cursor.execute("SELECT total_comision FROM comisiones_diarias WHERE fecha = ?", (fecha_sel,))
        resultado = self.cursor.fetchone()
        if resultado:
            self.ids.lbl_historial_dia.text = f"Caja ya guardada en esta fecha: ${resultado[0]:,.2f} ⚠️"
            self.ids.lbl_historial_dia.color = (1, 0.5, 0, 1)
        else:
            self.ids.lbl_historial_dia.text = "Sin registros guardados para esta fecha. ¡Puedes cargar!"
            self.ids.lbl_historial_dia.color = (0, 0.8, 1, 1)
            
        self.calcular_totales()

    def acumular_juegos_por_fechas(self, lista_fechas):
        for f in lista_fechas:
            self.cursor.execute("SELECT monto FROM ventas_acumuladas WHERE fecha = ? AND juego = 'Quini 6'", (f,))
            r_q = self.cursor.fetchone()
            if r_q and r_q[0]: self.quini_arrastrado += r_q[0]

            self.cursor.execute("SELECT monto FROM ventas_acumuladas WHERE fecha = ? AND juego = 'Loto'", (f,))
            r_l = self.cursor.fetchone()
            if r_l and r_l[0]: self.loto_arrastrado += r_l[0]

    def calcular_totales(self):
        try:
            fecha_dt_calculo = datetime.strptime(
                self.get_fecha_seleccionada(), "%Y-%m-%d"
            )
            dia_semana_calculo = fecha_dt_calculo.weekday()
        except ValueError:
            fecha_dt_calculo = None
            dia_semana_calculo = None

        juegos_quiniela = [
            (self.ids.q_previa, self.ids.lbl_q_previa), (self.ids.q_primera, self.ids.lbl_q_primera),
            (self.ids.q_matutina, self.ids.lbl_q_matutina), (self.ids.q_vespertina, self.ids.lbl_q_vespertina),
            (self.ids.q_nocturna, self.ids.lbl_q_nocturna), (self.ids.p_15, self.ids.lbl_p_15),
            (self.ids.p_21, self.ids.lbl_p_21), (self.ids.mp_12, self.ids.lbl_mp_12),
            (self.ids.mp_18, self.ids.lbl_mp_18)
        ]
        
        suma_venta = 0.0
        suma_comision = 0.0
        suma_rendir = 0.0

        # 1. Quinielas y Poceadas (12.42%) ingresadas hoy
        for campo_txt, label_res in juegos_quiniela:
            try:
                venta = float(campo_txt.text) if campo_txt.text else 0.0
                comision = venta * 0.1242
                rendir = venta - comision
                label_res.text = f"${rendir:,.2f}"
                suma_venta += venta
                suma_comision += comision
                suma_rendir += rendir
            except ValueError:
                label_res.text = "$0.00"

        # CORRECCIÓN TELEKINO: Calculamos el valor individual en su etiqueta, pero...
        try:
            venta_tk_hoy = float(self.ids.tk.text) if self.ids.tk.text else 0.0
            comision_tk_hoy = venta_tk_hoy * 0.10
            rendir_tk_hoy = venta_tk_hoy - comision_tk_hoy
            self.ids.lbl_tk.text = f"${rendir_tk_hoy:,.2f}"
            
            # ¡REGLA CLAVE! Solo se suma al total diario de HOY si es SÁBADO.
            # Los demás días se guarda en la BD pero no afecta la caja líquida de ese día.
            if dia_semana_calculo == 5:
                suma_venta += venta_tk_hoy
                suma_comision += comision_tk_hoy
                suma_rendir += rendir_tk_hoy
        except ValueError:
            self.ids.lbl_tk.text = "$0.00"

        # Quini 6 y Loto: incluir la venta ingresada HOY solamente
        # los miércoles y sábados, días en los que se liquida el acumulado.
        dia_semana = dia_semana_calculo
        try:
            venta_quini_hoy = float(self.ids.quini_val.text) if self.ids.quini_val.text.strip() else 0.0
            venta_loto_hoy = float(self.ids.loto_val.text) if self.ids.loto_val.text.strip() else 0.0
        except ValueError:
            venta_quini_hoy = 0.0
            venta_loto_hoy = 0.0

        # 2 = miércoles, 5 = sábado. En otros días quedan archivados
        # para la liquidación correspondiente, pero no afectan la caja diaria.
        if dia_semana in (2, 5):
            comision_quini_hoy = venta_quini_hoy * 0.1104
            rendir_quini_hoy = venta_quini_hoy - comision_quini_hoy
            comision_loto_hoy = venta_loto_hoy * 0.0735
            rendir_loto_hoy = venta_loto_hoy - comision_loto_hoy

            suma_venta += venta_quini_hoy + venta_loto_hoy
            suma_comision += comision_quini_hoy + comision_loto_hoy
            suma_rendir += rendir_quini_hoy + rendir_loto_hoy

        # 3. Calcular comisiones de los ARRASTRES ACUMULADOS de días previos (Solo impactan Miércoles o Sábado)
        comision_quini = self.quini_arrastrado * 0.1104
        rendir_quini = self.quini_arrastrado - comision_quini
        
        comision_loto = self.loto_arrastrado * 0.0735
        rendir_loto = self.loto_arrastrado - comision_loto
        
        comision_tk_arr = self.telekino_arrastrado * 0.10
        rendir_tk_arr = self.telekino_arrastrado - comision_tk_arr

        # Totales Consolidados Finales (Si es sábado, incluye el arrastre del viernes de memoria)
        total_venta_final = suma_venta + self.quini_arrastrado + self.loto_arrastrado + self.telekino_arrastrado
        total_comision_final = suma_comision + comision_quini + comision_loto + comision_tk_arr
        total_rendir_final = suma_rendir + rendir_quini + rendir_loto + rendir_tk_arr
        
        if dia_semana_calculo == 5: # Si es Sábado
            total_rendir_final += self.total_rendir_viernes

        self.venta_juegos_hoy = total_venta_final
        self.comision_juegos_hoy = total_comision_final
        self.rendir_juegos_hoy = total_rendir_final

        # Mostrar abajo de todo
        self.ids.lbl_total_vendido.text = f"TOTAL VENDIDO DEL DÍA: ${total_venta_final:,.2f}"
        self.ids.lbl_total_comision.text = f"TOTAL COMISIÓN ACUMULADA: ${total_comision_final:,.2f}"
        self.ids.lbl_total_rendir.text = f"TOTAL A RENDIR FINAL: ${total_rendir_final:,.2f}"

    def guardar_caja_dia(self):
        fecha_sel = self.get_fecha_seleccionada()

        # Validar la fecha y todos los importes antes de borrar cualquier dato.
        # Así, si hay un valor inválido, las tablas existentes quedan intactas.
        try:
            fecha_dt = datetime.strptime(fecha_sel, "%Y-%m-%d")
            campos_numericos = [
                self.ids.q_previa, self.ids.q_primera, self.ids.q_matutina,
                self.ids.q_vespertina, self.ids.q_nocturna, self.ids.p_15,
                self.ids.p_21, self.ids.mp_12, self.ids.mp_18, self.ids.tk,
                self.ids.quini_val, self.ids.loto_val,
            ]
            for campo in campos_numericos:
                texto = (campo.text or "").strip()
                if texto:
                    float(texto)

            # Asegura que se guarden los totales correspondientes a los importes actuales.
            self.calcular_totales()

            venta_quini_hoy = float(self.ids.quini_val.text.strip()) if self.ids.quini_val.text.strip() else 0.0
            venta_loto_hoy = float(self.ids.loto_val.text.strip()) if self.ids.loto_val.text.strip() else 0.0
            venta_tk_hoy = float(self.ids.tk.text.strip()) if self.ids.tk.text.strip() else 0.0

            # Si se vuelve a guardar una fecha, se reemplaza por completo su información:
            # se borran ambas tablas para esa fecha antes de insertar la carga corregida.
            # El bloque `with` hace que todo se confirme junto o se revierta en caso de error.
            with self.conexion:
                self.cursor.execute(
                    "DELETE FROM comisiones_diarias WHERE fecha = ?", (fecha_sel,)
                )
                self.cursor.execute(
                    "DELETE FROM ventas_acumuladas WHERE fecha = ?", (fecha_sel,)
                )

                self.cursor.execute("""
                    INSERT INTO comisiones_diarias
                        (fecha, total_vendido, total_comision, total_rendir)
                    VALUES (?, ?, ?, ?)
                """, (
                    fecha_sel,
                    self.venta_juegos_hoy,
                    self.comision_juegos_hoy,
                    self.rendir_juegos_hoy,
                ))

                # Se almacenan únicamente importes positivos. Como arriba se borró
                # la fecha completa, los valores antiguos que ahora estén vacíos
                # o en cero ya no quedan guardados por accidente.
                if venta_quini_hoy > 0:
                    self.cursor.execute(
                        "INSERT INTO ventas_acumuladas (fecha, juego, monto) VALUES (?, 'Quini 6', ?)",
                        (fecha_sel, venta_quini_hoy),
                    )
                if venta_loto_hoy > 0:
                    self.cursor.execute(
                        "INSERT INTO ventas_acumuladas (fecha, juego, monto) VALUES (?, 'Loto', ?)",
                        (fecha_sel, venta_loto_hoy),
                    )
                if venta_tk_hoy > 0:
                    self.cursor.execute(
                        "INSERT INTO ventas_acumuladas (fecha, juego, monto) VALUES (?, 'Telekino', ?)",
                        (fecha_sel, venta_tk_hoy),
                    )

        except ValueError as error:
            self.ids.lbl_historial_dia.text = (
                "No se guardó: revisá la fecha y los importes ingresados."
            )
            self.ids.lbl_historial_dia.color = (1, 0.3, 0.3, 1)
            print(f"Error de fecha o formato numérico: {error}")
            return
        except sqlite3.Error as error:
            self.ids.lbl_historial_dia.text = "Error al guardar. Los datos anteriores se conservaron."
            self.ids.lbl_historial_dia.color = (1, 0.3, 0.3, 1)
            print(f"Error de base de datos: {error}")
            return

        dia_semana = fecha_dt.weekday()
        # Mantener la regla existente del arrastre de caja del viernes al sábado.
        if dia_semana == 4:
            self.total_rendir_viernes = self.rendir_juegos_hoy
            print(f"Caja provisoria del Viernes guardada en memoria: ${self.total_rendir_viernes:,.2f}")
        elif dia_semana == 5:
            self.total_rendir_viernes = 0.0

        self.limpiar_pantalla_carga()
        self.on_fecha_cambiada()
        print(f"Planilla {fecha_sel} asentada correctamente; se reemplazaron los registros previos de esa fecha.")

    def limpiar_pantalla_carga(self):
        campos = [
            self.ids.q_previa, self.ids.q_primera, self.ids.q_matutina, self.ids.q_vespertina, self.ids.q_nocturna,
            self.ids.p_15, self.ids.p_21, self.ids.mp_12, self.ids.mp_18, self.ids.tk, self.ids.quini_val, self.ids.loto_val
        ]
        for c in campos: c.text = ""
        self.calcular_totales()

class AzarApp(App):
    def build(self): return CalculadorScreen()

if __name__ == '__main__':
    AzarApp().run()