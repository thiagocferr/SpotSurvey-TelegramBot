# SpotSurvey-TelegramBot

[**Link do repositório**](https://github.com/thiagocferr/SpotSurvey-TelegramBot) <https://github.com/thiagocferr/SpotSurvey-TelegramBot>

SpotSurveyBot é um bot de Telegram que permite que, a partir de informações coletadas durante a interação com o usuário em um cliente do Telegram, se preencha uma playlist no Spotify com músicas recomendadas baseadas nesses dados coletados. Ele foi desenvolvido como projeto final da disciplina _MAC0546(2020) - Fundamentos da Internet das Coisas_.

Em resumo, há comandos que iniciarão uma interação com o usuário onde ele selecionará _seeds_ (_top_ artistas ou músicas do usuário) e/ou parâmetros subjetivos de preferências musicais, que serão utilizadas para o preenchimento de uma playlist do Spotify associada à conta do usuário do bot com músicas recomendadas para ele. A recomendação das músicas não é feita pelo bot, mas sim pelo próprio Spotify.

De modo geral, a utilização do bot funciona da seguinte forma: o usuário deve realizar o processo de autenticação com o Spotify (através do comando `/login`), selecionar _seeds_ que gostaria de usar na recomendação (com comando `/setup_seed`), opcionalmente selecionar atributos que indicarão a preferência do usuário (caso não sejam definidas, as músicas recomendadas serão músicas similares às _seeds_ selecionadas), quando quiser gerar uma nova playlist (excluindo as músicas anteriores da playlist criada pelo bot e colocando músicas recomendadas), utilizar o comando `/generate_playlist` e, se quiser se desassociar do bot, excluindo informações registradas, o acesso a sua conta pelo bot e, opcionalmente, a última versão da playlist gerada pelo bot, utilizar o comando `/logout`.

Apesar de muitos casos onde a interação com o usuário poderia gerar erros terem sido tratados, é possível que existam alguns tipos de interações que não foram planejadas. Para maior confiança no funcionamento geral do bot, recomendo seguir o modo como as interações foram pensadas, o que está descrito na seção '**Utilizando o Bot**'

_Nota_: No estado atual do projeto, a sua utilização pública não é recomendada, visto a falta de testes suficientes para garantir a estabilidade do programa sobre diversas situações (por exemplo, não foram feitos muitos testes sobre seu funcionamento com a utilização simultânea por vários usuários, apesar do desenvolvimento em geral ter considerado isso de forma superficial). Além disso, o modo como está estruturado iria requerer algumas mudanças para permitir que o programa parasse de depender do serviço do _localtunnel_ para utilizar um servidor com domínio registrado e SSL para proteção dos dados enviados (visto que há troca de _tokens_ de acesso do Spotify durante as operações do bot).

## _Setup_ do bot (para reprodução)

O SpotSurveyBot é executado como um conjunto de _containers_ do Docker, mas antes de executá-los, alguns passos adicionais são necessários.

Antes mais nada, o código do bot utiliza um arquivo que guarda variáveis de ambiente chamado `.env`. Como ele guarda os tokens de acesso às APIs usadas (Telegram e Spotify), ele não está presente nesse repositório. No seu lugar, existe um arquivo `.env_model` que possui os campos que devem ser definidos para execução do bot. Quando for executar, renomeie o arquivo de `.env_model` para `.env` e preencha os campos vazios com as informações relevantes (o que será mencionado mais adiante).

### 1º passo: Registro de um bot no Telegram

Primeiramente, você deve possuir uma conta no [Telegram](https://web.telegram.org) e iniciar um conversa com [BotFather](https://telegram.me/BotFather), um perfil que serve para registro de bots no Telegram. Você deverá então criar um bot. Para mais informações sobre como criar um bot usando o BotFather, acesse <https://core.telegram.org/bots#6-botfather>.

Alguns detalhes sobre a criação do bot:

- O _name_ do bot pode pode ser o que você quiser

- O _Username_ do bot, além de seguir a restrição de terminar em 'bot' (como mencionado na criação de bots), deve ser único. Não poderá ser nomeado 'SpotSurveyBot' ou 'SpotSurveyTestBot', visto que já tenho ambos os nomes registrados a minha conta.

- Como mencionado no tutorial de criação de bots, você pode adicionar quais comandos existirão no bot (com o comando do BotFather '**/setcommands**'). Isso é útil pois facilita o uso dos comandos do bot ao permitir _autocomplete_. A lista de comandos que esse bot aceita está descrita na subseção **Lista de comandos**, seção **Utilizando o Bot**.

- O SpotSurveyBot só funciona em chats privados (ou seja, não pode ser adicionado em grupos). Se quiser garantir isso, use o comando '**/setjoingroups**' do bot para o estado **disabled**.

Após o registro, você receberá o _token_ de autorização de uso do bot que você acabou de criar. Copie o _token_ e o associe à variável **TELEGRAM_TOKEN** no arquivo `.env` (que você deverá ter obtido ao renomear o arquivo `.env_model`). Também preencha o campo **telegramBotLink** do arquivo `webserver/config.yaml` com a URL do bot criado (por exemplo, '<https://telegram.me/SpotSurveyBot>', substituindo 'SpotSurveyBot' pelo _Username_ dado ao bot)

### 2º passo: Registro de aplicação no Spotify

Para utilizar a API do Spotify, necessária para o funcionamento do SpotSurveyBot, deve-se primeiro registrar a aplicação na [_dashboard_](https://developer.spotify.com/dashboard/login) do Spotify. Para isso, uma conta do Spotify é necessária.

Após se logar com sua conta Spotify, crie uma aplicação. Após isso, você irá para a _dashboard_ de sua aplicação. Lá você encontrará o seu **Client ID** e, escondido sob um botão, o seu **Client Secret**, dois _tokens_ necessários para o funcionamento do bot. Copie eles para as variáveis **SPOTIFY_CLIENT_ID** e **SPOTIFY_CLIENT_SECRECT** do arquivo `.env`, respectivamente. Note que você precisará adicionar uma URI de redirecionamento em _edit settings_, sendo esse o endereço para o qual o usuário será redirecionado ao aceitar (ou negar) o acesso da aplicação a certas informações e operações sobre sua conta. O valor a ser colocado será tópico do próximo passo.

### 3º passo: Configurando servidores e _tunneling_

Como o SpotSurveyBot é basicamente um servidor que recebe atualizações do Telegram quando há uma interação com o usuário, até poderíamos criar um servidor local. Porém, isso não foi possível com esse bot por dois fatores: pessoas que não estão conectadas na rede local não conseguiriam interagir com o bot e, da forma como o [processo de autenticação da API do Spotify](https://developer.spotify.com/documentation/general/guides/authorization-guide/#authorization-code-flow) funciona, após o usuário permitir a aplicação se conectar com o Spotify, ocorre um redirecionamento para uma URL. Como a intenção era que o bot pudesse ser acessado de qualquer lugar, essa URL teria que ser um domínio registrado. Como pessoalmente não possuo nenhum domínio registrado ou servidor externo que possa rodar o bot, resolvi usar um serviço de tunelamento de um domínio específico para um servidor local. Mais especificamente, usei o [localtunnel](https://github.com/localtunnel/localtunnel).

Da forma como o projeto está configurado, há dois serviços (_docker containers_) que rodam instâncias do _localtunnel_ sobre dois subdomínios diferentes: o primeiro redireciona para a porta 5000 e conecta à internet (sob um domínio fixo) um servidor web local criado com Flask. O segundo redireciona para a porta 5001 e permite o estabelecimento de um _Webhook_ do Telegram, permitindo acesso às atualizações vindas do Telegram. Você deve então:

- Escolher dois subdomínios únicos para os serviços do _localtunnel_ e colocar seus nomes após a opção '--subdomain' no campo **services[localtunnel_web][command]** e **services[localtunnel_bot][command]**, no arquivo `docker-compose.yml`. É imprescindível para o funcionamento correto do bot que esses sejam subdomínios únicos. Para checar se os subdomínios selecionados estão disponíveis, você pode instalar a aplicação CLI do _localtunnel_ usando `npm install -g localtunnel` e rodar o túnel usando `lt --port 5000 --subdomain your-sub-domain-here`, ou você pode checar o _log_ dos _containers_ rodando os serviços do _localtunnel_ ao executar todos os serviços do _docker-compose_ conjuntamente (explicado nos próximos passos) e verificar se a URL alocada para você possui o subdomínio selecionado (algo similar a `https://your-sub-domain-here.loca.lt`), caso ele já não esteja sendo usado por alguém, ou se ele possui um subdomínio aleatório, caso contrário.

- Verificando que os subdomínios escolhidos não estão sendo usados e conseguindo as URLs alocadas para você, registre a URL que será alocada pelo serviço **localtunnel_web** do _docker-compose_, com um '/callback' no fim (algo como `https://your-sub-domain-for-webserver-here.loca.lt/callback`) tanto no arquivo `bot/config.yaml`, campo **spotify[url][redirectURL]**, quanto nas configuração do _dashboard_ de sua aplicação no Spotify (cliquem em _edit settings_ e adicione essa URL no campo _redirect URIs_).

- Também será necessário registrar a URL associada ao serviço **localtunnel_bot** do _docker-compose_ (algo como `https://your-sub-domain-for-bot-here.loca.lt/`) no arquivo `bot/config.yaml`, campo **spotify[telegram][webhookURL]**.

_**Nota importante**_: O funcionamento dos serviços do _localtunnel_ não é perfeito. Caso os subdomínios escolhidos sejam fáceis, outros usuários poderão ocupá-los. Um _bug_ recente que pode acontecer é você não poder mais acessar um subdomínio que teoricamente ninguém está utilizando caso haja uma interrupção abrupta na sua conexão com a internet (caso ela caia ou você suspenda seu computador). Nesses casos, as operações desse passo deverão ser refeitas. Outra possibilidade é do serviço parar por erro interno dos servidores que hospedam o _localtunnel_. Nesses casos, os _containers_ responsáveis pela comunicação com o _localtunnel_ em teoria irão reiniciar, o que pode resolver o problema (caso contrário, uma possível solução seria reiniciar o processo do _docker-compose_).


### 4º passo: Iniciando bot

Chegando aqui, tudo o que resta é executar os _containers_ do _Docker_ utilizando o _docker-compose_. Para isso, primeiro tenha instalado e corretamente configurado o [Docker-Compose](https://docs.docker.com/compose/install/). Para iniciar o bot, execute o seguinte comando sobre a pasta raiz do projeto:

```bash
docker-compose up --build
```

Isso irá criar as imagens do servidor web e do bot e utilizará as imagens do Redis, que servirá como banco de dados do bot, e os serviços do _localtunnel_, que serão conectados ao seus respectivos serviços.

_**Nota importante**_: **Caso** o bot não esteja conseguindo se comunicar com o Telegram (quando você manda mensagens ou comandos que supostamente deveriam ter algum retorno do Bot), tente comentar a linha 178 do arquivo `bot/bot.py`. Em testes anteriores, o bot funcionava com a linha comentada, mas ao fazer um teste em uma versão "pura" do código (clonando o repositório do Github), rodar essa linha de código permitiu a conexão do bot com o Telegram.

## Utilizando o Bot

Como mencionado no passo 1 do _Setup_ do bot, o bot é utilizável em clientes de Telegram acessando o _link_ associado que depende de seu _Username_ (se ele for 'SpotSurveyBot', acessando o _link_ '<https://telegram.me/SpotSurveyBot>' irá te direcionar para o bot). Acessando o _link_ e entrando no _chat_ associado ao bot, o usuário irá ver um botão escrito 'Começar' na parte de baixo. Ao clicar nele, o usuário inicia a conversa com o bot (esse é um comportamento padrão para a maioria dos bots de Telegram).

É interessante destacar que o bot funciona exclusivamente em _chat_ privado com os usuários, sendo que todas as informações armazenadas sobre um usuário do Telegram não estão associadas ao usuário em si, mas sim ao _chat_ que o usuário mantém com o bot.

### Lista de comandos

Para conseguir uma lista dos comandos disponíveis ao usuário para serem utilizados em momentos que não sejam durante a execução de outro desses comandos (alguns comandos iniciam uma 'conversa' com o usuário, onde esses comandos não deveriam ser utilizados para não interromper o fluxo da conversa e, possivelmente, gerar erros de execução), execute o comando `/help`. Esses comandos são:

- `/start`: Em uso normal retorna a mensagem de introdução do bot

- `/login`: Usado para obter acesso a informações e conseguir realizar operações sobre a conta Spotify do usuário através do [processo de autenticação da API do Spotify](https://developer.spotify.com/documentation/general/guides/authorization-guide/#authorization-code-flow).

- `/setup_seed`: Inicia uma conversa com o usuário onde ele seleciona quais itens ele gostaria de selecionar como _seeds_ para a recomendação (de 1 a 5 itens entre artistas e músicas). A interação com o usuário é feita através de menus de seleção e o usuário escolhe os itens enviando mensagens no chat com os números associados a eles (mais detalhes em seção própria)

- `/setup_attributes`: Comando opcional que inicia uma conversa com usuário onde ele irá receber uma mensagem perguntando o nível de um certo atributo que ele deseja selecionar para a recomendação de músicas, enviará uma mensagem com o número associado, e receberá a próxima mensagem pergunta o nível de outro atributo. Atributos do tipo Level servem com uma indicação da preferência do usuário, enquanto as do tipo Range excluem músicas com atributos fora do faixa de valores associada.

- `/get_setup`: Retorna mensagem com as escolhas feitas pelo usuário durante comandos `/setup_seed` e `/setup_attributes`

- `/generate_playlist`: Troca músicas atuais da playlist do Spotify pelas músicas recomendadas, utilizando os parâmetros selecionados durante os comandos `/setup_seed` e `/setup_attributes`

- `/logout`: Exclui todos os dados relacionados ao usuário (mais especificamente, do chat utilizado), opcionalmente excluindo a playlist gerada.

### Primeiro passo: _Login_ com conta do Spotify

Todas as operações principais do SpotSurveyBot necessitam que o usuário se autentique com sua conta Spotify, permitindo assim que o bot obtenha dados necessários e permissão para fazer operações sobre a conta do usuário que utiliza o SpotSurveyBot. Para tanto, como explicado durante a mensagem de início do bot, utilize o comando `/login` para iniciar o processo.

Será enviado uma mensagem com um link embutido. Acessando o link, ele dará em uma página de autenticação de usuário do Spotify (caso o usuário já não tenha realizado essa operação antes), onde o usuário se logará em sua conta Spotify, e, após isso, outra página irá pedir sua aprovação sobre a disponibilização de certos dados e permissão de certas operações para a aplicação registrada no Spotify (ver 2º passo do _setup_). Caso aceite, o usuário será redirecionado para uma página de alerta do _localtunnel_, que avisará dos potenciais riscos que acessar páginas desse domínio associadas ao _localtunnel_ podem trazer (caso nunca passado por essa página antes). Como esse aviso se referencia ao programa desenvolvido aqui, publicamente disponível, basta prosseguir que o usuário será redirecionado para um cliente do Telegram.

Retornando ao Telegram, pressione o botão 'Começar' para efetuar o login. Juntamente com isso, a playlist do spotify que será criado em seu usuário e associada ao seu chat com o bot será criada.

### Segundo passo: Associar _seeds_ ao usuário (chat)

Antes de se gerar uma playlist com músicas recomendadas, é necessária que o usuário dê algumas informações sobre suas preferências atuais em músicas. Essas informações serão utilizadas no processo de recomendação de músicas.

Para recomendar músicas, a API do Spotify apenas exige que um conjunto de 1 a 5 itens entre artista, músicas ou gêneros seja especificado. O comando `/setup_seed` é responsável por coletar essas informações. Ele permite que o usuário escolha 5 itens entre os 30 _top_ artistas e as 50 _top_ faixas relacionados à conta do Spotify do usuário (o conceito de _top_ vem do próprio Spotify). Para garantir que haja ao menos algumas recomendações (o máximo são 20 músicas, mas pode ser 0 também), sugere-se não escolher somente artistas muito pouco conhecidos ou faixas muito pouco reproduzidas.

Após executar o comando e iniciar a 'conversa', o usuário irá se deparar com uma mensagem que serve como um tipo de menu, mostrando os itens (artistas ou músicas) em páginas de 10 itens cada, com informações sobre eles (para artistas, um link para seu perfil no Spotify e quais gêneros de músicas estão associados a ele, para músicas, um link para a música no Spotify e quais artistas participaram dela). Para ir navegar entre as páginas, o usuário usa os botões 'Previous' e 'Next'. Para ir do modo de seleção entre artistas e músicas, há um botão que faz essa troca ('Select Artists/Tracks'). Para seleciona um ou mais itens de um tipo, o usuário deve estar em uma página correspondente ao tipo de item que quer selecionar (uma indicação de que tipo de página se está, além da estrutura da listagem de itens, são as mensagens presentes no topo e no fim dela) e mandar uma mensagem com os números que deseja selecionar, separados por vírgula. Quando acabar de selecionar os itens, basta pressionar o botão 'Done', que irá confirmar se o usuário gostaria de encerrar o processo. Se sim, as músicas e/ou artistas selecionados serão salvos no banco de dados, associados ao usuário/chat que está usando.

### Terceiro passo (opcional): Definir parâmetros para recomendação de músicas

Em teoria, somente as _seeds_ são necessárias para poder pedir à API do Spotify por recomendação de músicas. Entretanto, o usuário pode também definir alguns parâmetros sobre as músicas que deseja ser recomendado utilizando o comando `/setup_attributes`.

Utilizando esse comando, usuários podem definir valores para atributos de duas formas: definindo um nível (**_Level_**) para o atributo, o que irá guiar a recomendação de músicas sem excluir as que possuem o atributo em questão fora do valor definido, ou irão definir um intervalo (**_Range_**) onde qualquer música do _pool_ de músicas que acompanha cada _seed_ selecionada (por experiência, cada _seed_ selecionada trazia cerca de 150 músicas) que possuir um certo atributo fora do intervalo definido será excluída da recomendação. Pode-se imaginar que, ao se definir muitos atributos como do tipo _Range_ ou selecionar intervalos de valores muito distintos dos disponíveis no _pool_ de músicas disponíveis, chega-se fácil num resultado de que nenhuma música é recomendada. E foi exatamente o que aconteceu numa primeira versão do bot. Por isso, a maioria da seleção de atributos só pode ser do tipo _Level_, como forma de reduzir a incidência de vezes em que nenhuma música é recomendada para o usuário (apesar de isso ainda poder acontecer, caso as _seeds_ selecionadas sejam somente de artistas muito pouco conhecidos ou músicas com baixo número de reproduções). A lógica do funcionamento desses dois tipos de seleção de atributos ainda existe; o que foi alterado foi só a exclusão das perguntas que geravam a seleção de atributos do tipo _Range_, com a exceção do atributo 'Duration'.

Explicado isso, o funcionamento do comando é o seguinte: após iniciar o processo, será mostrada uma mensagem que indica qual atributo será definido e qual o seu tipo (como citado anteriormente, a maioria é do tipo _Level_) (a seleção do atributo pode ser ignorada também, caso o usuário não tenha nenhuma preferência sobre um atributo específico). O usuário seleciona alguma das opções enviando uma mensagem com o número associado com a opção desejada  (caso queria cancelar a operação, enviar o comando `/cancel`). Após enviar uma resposta válida, a próxima seleção é apresentada, repetindo o processo até a última seleção de atributo.

### Quarto passo (opcional): Checar as _seeds_ e os parâmetros definidos

Antes de executar o comando de gerar uma playlist recomendada (`/generate_playlist`), o usuário pode checar o que será utilizado durante na geração das recomendações: as _seeds_ selecionadas com o comando `/setup_seed` e/ou os atributos selecionados com o comando `/setup_attributes`.

### Quinto passo: Gerar a playlist:

Após definir parâmetros, vem então o passo principal: conseguir uma lista de músicas recomendadas, remover as músicas antigas da playlist associada ao usuário e colocar as novas músicas recomendadas. E é exatamente isso que o comando `generate_playlist` faz.

Vale mencionar aqui que a recomendação das músicas em si não é feita pelo bot, mas sim por serviços internos do Spotify. O que o bot faz é coletar informações através do usuário que serão colocadas como parâmetros para uma requisição à API do Spotify e receberá uma recomendação de músicas dela.

### Sexto passo: E agora?

Após conseguir gerar as músicas, não há muito mais o que o bot possa fazer. O usuário pode num tempo futuro, alterar as _seeds_ ou os atributos utilizados para conseguir novos tipos de recomendações (como já teria suas informações básicas registradas, não haveria necessidade de se logar de novo, bastando começar o processo do passo dois, por exemplo).

Caso o usuário queria, é possível se desvincular completamente do bot, excluindo todas informações registradas sobre ele, usando o comando `/logout`. O comando permite também a exclusão da playlist associada ao usuário do próprio Spotify. Note que, caso opte por não excluir a playlist e vá realizar o processo de login novamente (com o comando `/login`), uma nova playlist de mesmo nome será criada e a playlist antiga não sofrerá atualizações quando se realizar o processo de geração de músicas recomendadas, sendo o alvo dessa operação somente a playlist mais nova (a que ainda está associada ao usuário no Telegram).

