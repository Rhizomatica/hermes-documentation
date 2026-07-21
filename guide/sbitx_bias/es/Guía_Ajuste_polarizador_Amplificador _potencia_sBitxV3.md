# 🔧 Guía de Ajuste de Polarización del PA - sBitx V3

Esta guía describe el proceso paso a paso para ajustar la **polarización del Amplificador de Potencia (PA)** en el sBitx V3, garantizando el rendimiento óptimo de los MOSFETs IRF510 en la etapa de PA. Este procedimiento se puede realizar en cualquier momento, sin embargo es **obligatorio** cuando se reemplazan los IRF510.

---

## 📋 Prerrequisitos

### 🛡️ Consideraciones de Seguridad

- Siempre conecte el sBitx a una **carga ficticia de 50 ohmios** y a un **medidor de potencia** para evitar dañar los MOSFETs al transmitir en una carga abierta o desequilibrada.

### 🛠️ Herramientas Necesarias

- **Multímetro**: Para medir el consumo de corriente.
- **Destornillador de pala plana o herramienta de ajuste**: Para ajustar el potenciómetro de polarización.
- **Fuente de alimentación estable de 12,1-13,8 VCC**: Con límite de corriente, capaz de suministrar hasta **2A máx.**.

---

## 📖 Descripción General del MOSFET IRF510

- El **IRF510** es un MOSFET de canal N de modo de enriquecimiento, no diseñado específicamente para RF pero a veces utilizado en amplificadores de radioaficionado.
- Requiere **polarización precisa** para operar en la región lineal (Clase AB para SSB/CW) para evitar fugas térmicas.

### 🧠 Notas sobre el sBitx V3

- El sBitx V3 utiliza **dos MOSFETs IRF510** en su etapa de PA, con polarización ajustada a través del **potenciómetro PA_BIAS1**.
- El ajuste adecuado de la polarización garantiza una amplificación limpia con mínimo calor y distorsión, preservando la longevidad de los MOSFETs.

---

## 📝 Procedimiento de Ajuste de Polarización Paso a Paso

### 1️⃣ Preparación de la Configuración

1. Conecte el sBitx V3 a una **carga ficticia de 50 ohmios** y a un **medidor de potencia**.
2. Abra la carcasa del transceptor y localice el **potenciómetro PA_BIAS1** en la placa de circuito del sBitx V3 *(consulte el esquema en la carpeta de documentación)*.
3. Gire el **potenciómetro PA_BIAS1** completamente en el **sentido antihorario** (polarización mínima, corriente cero).
4. Conecte el multímetro o medidor de corriente **en serie con el conector de alimentación XT60** para monitorear el consumo de corriente.
5. Alimente el sBitx con una fuente de **12-13,8 VCC** (con límite de corriente de 2A máx.).
6. Asegure una refrigeración adecuada, ya que los IRF510 disipan ~1,38W con 100 mA de polarización en 13,8V (disipador de calor necesario).

---

### 2️⃣ Configuración Inicial

| Configuración | Valor |
|---------------|-------|
| **Frecuencia** | 7,035 MHz |
| **Modo** | USB |
| **Ganancia del Mic** | 0 o 1 (mínimo) |
| **Drive (Excitación)** | 0 o 1 (mínimo) |

> ⚠️ **Importante**: Asegúrese de que el **potenciómetro PA_BIAS1** esté completamente en el **sentido antihorario** (polarización mínima, corriente cero) antes de continuar.

---

### 3️⃣ Medir la Corriente de Reposo en TX

1. Active el **modo TX** presionando el **botón TX en el software** o el **PTT** en el micrófono externo.
   > 🚫 **No hable en el micrófono** durante este proceso.
2. Anote el **consumo de corriente CC** usando un multímetro de corriente CC en serie con la fuente de alimentación.

---

### 4️⃣ Ajustar la Corriente de Polarización

> ⚡ **ADVERTENCIA**: Ajuste el potenciómetro **LENTAMENTE**. **¡NO AUMENTE POR ENCIMA DE 250 mA!**

1. En **modo TX**, gire lentamente el **potenciómetro PA_BIAS1** en el **sentido horario** para aumentar la tensión de polarización en las compuertas de los IRF510.
2. Monitoree el **consumo total de corriente** en el multímetro y ajuste **LENTAMENTE** el **potenciómetro PA_BIAS1** hasta que aumente de **150 a 250 mA** por encima de la corriente de reposo registrada en el paso 3.

---

### 5️⃣ Verificar y Ajustar Finamente

1. Cambie al **modo RX** (a través del software o libere el PTT del micrófono) y deje que los MOSFETs se estabilicen durante unos segundos.
2. Reactive el **modo TX** y verifique que el aumento de corriente permanezca estable en **150-250 mA** por encima de la corriente de reposo.

| Condición | Acción |
|-----------|--------|
| **Demasiado alta** (>250 mA de aumento) | Reduzca la polarización ligeramente para evitar sobrecalentamiento o fuga térmica. |
| **Demasiado baja** (<150 mA) | Aumente la polarización ligeramente para garantizar una linealidad adecuada. |

3. Verifique la temperatura del disipador de calor de los IRF510. Debe estar **caliente pero no excesivamente caliente**. Reduzca la polarización o mejore la refrigeración si hay sobrecalentamiento.

---

### 6️⃣ Probar el Rendimiento en RF

1. Aumente gradualmente la configuración de **Drive (Excitación)** (por ejemplo, a 10-20) y transmita hacia la carga ficticia mientras monitorea la potencia de salida.
2. El sBitx V3 debe producir **~25W de salida** con excitación completa, dependiendo de la banda y la tensión de alimentación (12,1-13,8V).
3. Verifique la modulación SSB o la salida CW limpia. Si hay distorsión, reduzca ligeramente la polarización o asegúrese de que la excitación de entrada no supere los 2W para proteger los IRF510.
4. Confirme que la tensión de la fuente de alimentación esté estable (**12-13,8V**).

---

### 7️⃣ Calibración

> 📌 **Consejo**: Si la potencia de salida varía entre bandas, utilice la **utilidad V3 Powercal** para calibrar los ajustes de excitación para cada banda, compensando las variaciones de ganancia.

---

## 📊 Tabla Resumen

| Paso | Acción | Objetivo |
|------|--------|----------|
| 1 | Preparación de la Configuración | Conectar carga ficticia, medidor de potencia, localizar PA_BIAS1 |
| 2 | Configuración Inicial | Frecuencia: 7,035 MHz, Modo: USB, Drive/Ganancia de Mic mínimos |
| 3 | Medir Corriente de Reposo en TX | Registrar la corriente de base |
| 4 | Ajustar Corriente de Polarización | Aumentar en **150-250 mA** por encima de la corriente de reposo |
| 5 | Verificar y Ajustar Finamente | Polarización estable, verificar temperatura del disipador |
| 6 | Probar Rendimiento en RF | ~**25W** de salida, modulación limpia |
| 7 | Calibración | Usar utilidad V3 Powercal para ajustes por banda |

---

## ⚠️ Seguridad y Buenas Prácticas

- ✅ Siempre use una **carga ficticia de 50 ohmios** durante el ajuste.
- ✅ Mantenga la **fuente de alimentación con límite de corriente** en 2A máx.
- ✅ Realice los ajustes de polarización **lentamente**.
- ✅ Monitoree la **temperatura del disipador de calor** constantemente.
- ❌ **Nunca** transmita sin una carga adecuada.
- ❌ **Nunca** exceda 250 mA de aumento por encima de la corriente de reposo.

---

## 📚 Referencias

- [Esquema del sBitx V3](https://github.com/drexjj/sbitx/wiki/sBitx-V3-PA-Bias-Adjustment#sbitx-v3-pa-bias-adjustment-guide)
- [Manual del Usuario del sBitx V3](https://github.com/drexjj/sbitx/wiki)

---

## 📝 Historial de Revisiones

| Fecha | Versión | Autor | Descripción |
|-------|---------|-------|-------------|
| 2026-07-20 | 1.0 | Nilson Rocha | Creación inicial |
| | | | |

---

## 📬 Preguntas / Soporte

Para preguntas o soporte, por favor abra un issue en el repositorio o contacte al mantenedor.

---

**¡Buen Radioaficionado!** 🎙️📻