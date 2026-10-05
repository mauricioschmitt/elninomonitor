# Monitor El Niño 2026–27 · Mafra e região

Painel de monitoramento do El Niño com foco no agro do Planalto Norte Catarinense.

## O que se atualiza sozinho

| Parte do painel | Fonte | Frequência |
|---|---|---|
| Índices Niño semanais (1+2, 3, 3.4, 4) | NOAA/CPC (`wksst9120.for`) | robô diário (GitHub Actions) |
| Índice RONI (gráfico histórico) | NOAA/CPC (`RONI.ascii.txt`) | robô diário |
| Status do alerta, síntese e datas | NOAA/CPC, ENSO Diagnostic Discussion | robô diário |
| Previsão de 16 dias para Mafra | Open-Meteo | toda vez que a página abre |
| Chuva do ano em Mafra x média 1991–2020 | Open-Meteo (reanálise ERA5) | toda vez que a página abre |
| Imagem de satélite da anomalia de TSM | NOAA Coral Reef Watch | toda vez que a página abre |

**Atualização manual:** as probabilidades da NOAA (bloco `outlook` em `data/enso.json`) e os textos sobre a safra (Epagri/Cepa) dentro do `index.html`. A NOAA publica a discussão mensal na 2ª quinta-feira do mês; quando a data mudar, o painel mostra um aviso pedindo para revisar o bloco `outlook`.

## Como publicar no GitHub Pages

1. Crie um repositório público no GitHub (ex.: `monitor-el-nino`).
2. Envie todos os arquivos desta pasta, **incluindo a pasta oculta `.github`** (Add file → Upload files; arraste a pasta inteira).
3. Em **Settings → Pages**, escolha *Deploy from a branch*, branch `main`, pasta `/ (root)`. Em 1–2 minutos o site fica em `https://SEU-USUARIO.github.io/monitor-el-nino/`.
4. Em **Settings → Actions → General → Workflow permissions**, marque *Read and write permissions* (o robô precisa disso para salvar os dados).
5. Em **Actions → Atualizar dados do El Niño → Run workflow**, rode uma vez para testar. Depois ele roda sozinho todo dia.

Se o robô falhar em alguma fonte, ele mantém os dados anteriores, e o painel continua funcionando.

## Testar no computador

Abrir o `index.html` direto funciona, mas o navegador bloqueia a leitura do `data/enso.json` fora de um servidor (o painel usa os dados embutidos). Para testar como no site:

```
python -m http.server 8000
```
e abra `http://localhost:8000`.
