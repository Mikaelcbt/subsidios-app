# Configurar o Drive do escritório

A aba "Enviar pro Drive" usa uma conexão só, do escritório, e não a conta de cada operador.
O jeito recomendado é uma conta de serviço do Google adicionada como participante nos Drives
compartilhados das faixas (CÍVEL- Pan A - C, D - F, ... W - Z).

## Plano A: conta de serviço (recomendado)

1. Google Cloud Console (https://console.cloud.google.com): crie um projeto (ou use o que já existe).
2. APIs e serviços > Biblioteca > "Google Drive API" > Ativar.
3. IAM e administrador > Contas de serviço > Criar conta de serviço. Nome: `subsidios-drive`.
   Não precisa dar nenhum papel no projeto.
4. Abra a conta criada > aba Chaves > Adicionar chave > Criar nova chave > JSON. Um arquivo `.json` vai baixar.
   Guarde ele como senha: quem tem esse arquivo mexe nos Drives.
5. Copie o e-mail da conta (algo como `subsidios-drive@SEU-PROJETO.iam.gserviceaccount.com`).
6. No Google Drive do escritório, em CADA Drive compartilhado de faixa (os 8 "CÍVEL- Pan X - Y"):
   Gerenciar participantes > colar o e-mail > papel **Administrador de conteúdo** > Enviar.
   Precisa ser feito por alguém que é Administrador desses Drives.
7. Railway > serviço > Variables > New Variable:
   - `GOOGLE_SERVICE_ACCOUNT_JSON` = o conteúdo inteiro do arquivo `.json` (abre no bloco de notas, copia tudo e cola).
8. Deploy. No topo do app deve aparecer "Drive do escritório ok · 8 drives".

Se no passo 6 o Drive disser que não pode compartilhar com pessoas fora da organização, o Workspace
do escritório bloqueia participantes externos. Aí ou o admin do Workspace libera
(Admin console > Apps > Google Workspace > Drive e Docs > Configurações de compartilhamento >
permitir que Drives compartilhados tenham participantes externos), ou vá pro plano B.

## Plano B: conta Google do escritório

Usa uma conta do escritório que já participa dos 8 Drives.

1. No mesmo projeto do Google Cloud: APIs e serviços > Tela de consentimento OAuth. Tipo "Interno" se
   o projeto estiver dentro do Workspace do escritório; senão "Externo" e depois **Publicar app**
   (em modo "Teste" o token expira em 7 dias).
2. Credenciais > Criar credenciais > ID do cliente OAuth > Aplicativo da Web.
   URI de redirecionamento autorizado: `https://developers.google.com/oauthplayground`.
3. Abra https://developers.google.com/oauthplayground > engrenagem > "Use your own OAuth credentials" >
   cole Client ID e Client secret.
4. Escopo: `https://www.googleapis.com/auth/drive` > Authorize APIs > entre com a conta do escritório >
   Exchange authorization code for tokens > copie o **Refresh token**.
5. Railway > Variables:
   - `GOOGLE_CLIENT_ID`
   - `GOOGLE_CLIENT_SECRET`
   - `GOOGLE_ESCRITORIO_REFRESH_TOKEN`

Se `GOOGLE_SERVICE_ACCOUNT_JSON` existir, ele tem prioridade sobre o plano B.

## Opcional

- `DRIVE_FAIXAS_FILTRO` (padrão `PAN`): só Drives com esse texto no nome entram no mapa de faixas.
  O app lê a faixa no fim do nome ("... T - V") e ignora Drives sem faixa, como "Cível - PAN".
- `ENVIOS_DIR` (padrão `/tmp/subsidios-envios`): onde os arquivos ficam até subir. Apagados após 24h.

## Modo teste com uma pasta no Meu Drive (sem Workspace)

Pra testar o fluxo de verdade com uma conta Gmail comum. A conta de serviço não serve aqui porque
não tem espaço pra subir arquivo no Meu Drive de ninguém, então usa o plano B com a tua conta.

1. Google Drive (Meu Drive): crie uma pasta `SUBSIDIOS TESTE`. Dentro dela crie `CÍVEL- Pan T - V`,
   e dentro dessa crie as pastas `T`, `U` e `V`. Pode criar outras faixas do mesmo jeito se quiser.
2. Abra a pasta `SUBSIDIOS TESTE` e copie o ID do fim da URL
   (`https://drive.google.com/drive/folders/ESTE_PEDACO_AQUI`).
3. Google Cloud Console: crie um projeto e ative a "Google Drive API" (APIs e serviços > Biblioteca).
4. APIs e serviços > Tela de consentimento OAuth (ou "Google Auth Platform"): tipo **Externo**, nome do app
   qualquer, teu e-mail como suporte e contato. Em "Público-alvo" / "Usuários de teste", adicione o teu Gmail.
5. Credenciais > Criar credenciais > ID do cliente OAuth > Aplicativo da Web. Em "URIs de redirecionamento
   autorizados" coloque `https://developers.google.com/oauthplayground`. Guarde o Client ID e o Client secret.
6. Abra https://developers.google.com/oauthplayground. Na engrenagem (canto direito), marque
   "Use your own OAuth credentials" e cole Client ID e Client secret.
7. No campo "Input your own scopes" cole `https://www.googleapis.com/auth/drive` > Authorize APIs >
   entre com o teu Gmail. Vai aparecer "O Google não verificou este app": clique em Continuar.
8. Clique em "Exchange authorization code for tokens" e copie o **Refresh token**.
9. Railway > Variables (e não coloque `GOOGLE_SERVICE_ACCOUNT_JSON`):
   - `GOOGLE_CLIENT_ID`
   - `GOOGLE_CLIENT_SECRET`
   - `GOOGLE_ESCRITORIO_REFRESH_TOKEN`
   - `DRIVE_RAIZ_TESTE_ID` = o ID do passo 2
10. Depois do deploy, o topo do app mostra "Drive de TESTE ok · 1 faixas". Teste com um autor que comece com T.

Com o app em modo "Teste" no Google, o refresh token vale 7 dias. Se parar, repita os passos 7 e 8.
Pra ir pro escritório: apague `DRIVE_RAIZ_TESTE_ID` e `GOOGLE_ESCRITORIO_REFRESH_TOKEN` e configure o plano A.
