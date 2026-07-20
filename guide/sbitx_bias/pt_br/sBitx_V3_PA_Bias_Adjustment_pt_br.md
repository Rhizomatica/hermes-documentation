# 🔧 Guia de Ajuste de Polarização do PA - sBitx V3

Este guia descreve o processo passo a passo para ajustar a **polarização do Amplificador de Potência (PA)** no sBitx V3, garantindo o desempenho ideal dos MOSFETs IRF510 no estágio de PA. Este procedimento pode ser realizado a qualquer momento, porém é **obrigatório** quando os IRF510 são substituídos.

---

## 📋 Pré-requisitos

### 🛡️ Considerações de Segurança

- Sempre conecte o sBitx a uma **carga fantasma de 50 ohms** e a um **medidor de potência** para evitar danos aos MOSFETs ao transmitir em uma carga aberta ou desequilibrada.

### 🛠️ Ferramentas Necessárias

- **Multímetro**: Para medir o consumo de corrente.
- **Chave de fenda plana ou ferramenta de ajuste**: Para ajustar o potenciômetro de polarização.
- **Fonte de alimentação estável de 12,1-13,8 VCC**: Com limite de corrente, capaz de fornecer até **2A máx.**.

---

## 📖 Visão Geral do MOSFET IRF510

- O **IRF510** é um MOSFET de canal N de modo de enriquecimento, não projetado especificamente para RF, mas às vezes usado em amplificadores de rádio amador.
- Requer **polarização precisa** para operar na região linear (Classe AB para SSB/CW) para evitar fuga térmica.

### 🧠 Notas sobre o sBitx V3

- O sBitx V3 usa **dois MOSFETs IRF510** em seu estágio de PA, com polarização ajustada através do **potenciômetro PA_BIAS1**.
- O ajuste adequado da polarização garante amplificação limpa com mínimo calor e distorção, preservando a longevidade dos MOSFETs.

---

## 📝 Procedimento de Ajuste de Polarização Passo a Passo

### 1️⃣ Preparação da Montagem

1. Conecte o sBitx V3 a uma **carga fantasma de 50 ohms** e a um **medidor de potência**.
2. Abra o gabinete do transceptor e localize o **potenciômetro PA_BIAS1** na placa de circuito do sBitx V3 *(consulte o esquema na pasta de documentação)*.
3. Gire o **potenciômetro PA_BIAS1** completamente no **sentido anti-horário** (polarização mínima, corrente zero).
4. Conecte o multímetro ou medidor de corrente **em série com o conector de alimentação XT60** para monitorar o consumo de corrente.
5. Alimente o sBitx com uma fonte de **12-13,8 VCC** (com limite de corrente de 2A máx.).
6. Certifique-se de que há resfriamento adequado, pois os IRF510 dissipam ~1,38W com 100 mA de polarização em 13,8V (dissipador de calor necessário).

---

### 2️⃣ Configuração Inicial

| Configuração | Valor |
|--------------|-------|
| **Frequência** | 7,035 MHz |
| **Modo** | USB |
| **Ganho do Mic** | 0 ou 1 (mínimo) |
| **Drive (Excitação)** | 0 ou 1 (mínimo) |

> ⚠️ **Importante**: Certifique-se de que o **potenciômetro PA_BIAS1** esteja completamente no **sentido anti-horário** (polarização mínima, corrente zero) antes de prosseguir.

---

### 3️⃣ Medir a Corrente de Repouso em TX

1. Ative o **modo TX** pressionando o **botão TX no software** ou o **PTT** no microfone externo.
   > 🚫 **Não fale no microfone** durante este processo.
2. Anote o **consumo de corrente CC** usando um multímetro de corrente CC em série com a fonte de alimentação.

---

### 4️⃣ Ajustar a Corrente de Polarização

> ⚡ **ATENÇÃO**: Ajuste o potenciômetro **LENTAMENTE**. **NÃO AUMENTE ACIMA DE 250 mA!**

1. Em **modo TX**, gire lentamente o **potenciômetro PA_BIAS1** no **sentido horário** para aumentar a tensão de polarização nos gates dos IRF510.
2. Monitore o **consumo total de corrente** no multímetro e ajuste **LENTAMENTE** o **potenciômetro PA_BIAS1** até que ele aumente de **150 a 250 mA** acima da corrente de repouso registrada no passo 3.

---

### 5️⃣ Verificar e Ajustar Finamente

1. Alterne para o **modo RX** (via software ou solte o PTT do microfone) e deixe os MOSFETs estabilizarem por alguns segundos.
2. Reative o **modo TX** e verifique se o aumento de corrente permanece estável em **150-250 mA** acima da corrente de repouso.

| Condição | Ação |
|----------|------|
| **Muito alta** (>250 mA de aumento) | Reduza a polarização ligeiramente para evitar superaquecimento ou fuga térmica. |
| **Muito baixa** (<150 mA) | Aumente a polarização ligeiramente para garantir linearidade adequada. |

3. Verifique a temperatura do dissipador de calor dos IRF510. Deve estar **quente, mas não excessivamente quente**. Reduza a polarização ou melhore o resfriamento se houver superaquecimento.

---

### 6️⃣ Testar o Desempenho em RF

1. Aumente gradualmente a configuração de **Drive (Excitação)** (por exemplo, para 10-20) e transmita para a carga fantasma enquanto monitora a potência de saída.
2. O sBitx V3 deve produzir **~25W de saída** com drive total, dependendo da banda e da tensão de alimentação (12,1-13,8V).
3. Verifique a modulação SSB ou a saída CW limpa. Se houver distorção, reduza ligeiramente a polarização ou certifique-se de que o drive de entrada não exceda 2W para proteger os IRF510.
4. Confirme que a tensão da fonte de alimentação está estável (**12-13,8V**).

---

### 7️⃣ Calibração

> 📌 **Dica**: Se a potência de saída variar entre as bandas, use o **utilitário V3 Powercal** para calibrar as configurações de drive para cada banda, compensando as variações de ganho.

---

## 📊 Tabela Resumo

| Etapa | Ação | Alvo |
|-------|------|------|
| 1 | Preparação da Montagem | Conectar carga fantasma, medidor de potência, localizar PA_BIAS1 |
| 2 | Configuração Inicial | Frequência: 7,035 MHz, Modo: USB, Drive/Mic Gain mínimos |
| 3 | Medir Corrente de Repouso em TX | Registrar a corrente de base |
| 4 | Ajustar Corrente de Polarização | Aumentar em **150-250 mA** acima da corrente de repouso |
| 5 | Verificar e Ajustar Finamente | Polarização estável, verificar temperatura do dissipador |
| 6 | Testar Desempenho em RF | ~**25W** de saída, modulação limpa |
| 7 | Calibração | Usar utilitário V3 Powercal para ajustes por banda |

---

## ⚠️ Segurança e Boas Práticas

- ✅ Sempre use uma **carga fantasma de 50 ohms** durante o ajuste.
- ✅ Mantenha a **fonte de alimentação com limite de corrente** em 2A máx.
- ✅ Faça os ajustes de polarização **lentamente**.
- ✅ Monitore a **temperatura do dissipador de calor** constantemente.
- ❌ **Nunca** transmita sem uma carga adequada.
- ❌ **Nunca** exceda 250 mA de aumento acima da corrente de repouso.

---

## 📚 Referências

- [Esquema do sBitx V3](https://github.com/drexjj/sbitx/wiki/sBitx-V3-PA-Bias-Adjustment#sbitx-v3-pa-bias-adjustment-guide)
- [Manual do Usuário do sBitx V3](https://github.com/drexjj/sbitx/wiki)

---

## 📝 Histórico de Revisões

| Data | Versão | Autor | Descrição |
|------|--------|-------|-----------|
| 2026-07-20 | 1.0 | [Nilson Rocha ] | Criação inicial |
| | | | |

---

## 📬 Dúvidas / Suporte

Para dúvidas ou suporte, por favor abra uma issue no repositório ou entre em contato com o mantenedor.

---

**Bom Radioamadorismo!** 🎙️📻