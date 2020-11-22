# Organização do projeto: SpotSurveyBot

Por Thiago Cunha Ferreira, NUSP: 10297605


## Estrutura do projeto

A raiz do projeto inclui os seguintes arquivos:

- `README.md`: O arquivo falando sobre o projeto, como replicar e como utilizá-lo.

- `docker-compose.yml`: Arquivo do Docker-Compose que inicia todos os serviços necessários para o funcionamento do bot: o servidor que é o bot em si, o servidor web usado durante o processo de _login_, o banco de dados não-relacional Redis usado para armazenar informações sobre o usuário, e os dois processos do _localtunnel_, que permitem o acesso às funcionalidade do bot remotamente.

- `.env_model`: Arquivo que serve como modelo para o arquivo `.env`, que descreve algumas variáveis de ambiente que serão definidas durante a execução do projeto. Assim, renomeie esse arquivo para `.env` e preencha as variáveis com as informações necessárias (nome do projeto, token do Telegram Bot e tokens da aplicação do Spotify).

- `organizacao_projeto.md`: Esse arquivo, descrevendo a estrutura do projeto

Dentro da pasta raíz, temos duas pastas: `bot/` e `webserver/`

### bot

Pasta com todos os arquivos que constituem o formam a operação do bot do telegram SpotSurveyBot. Nele, podemos encontrar os seguintes arquivos:

- `config.yaml`: Arquivo de configurações gerais do bot. Alguns dos campos que ele possui são URL de acesso aos _endpoints_ da API do Spotify, as URL usadas para o Webhook (no qual o bot recebe atualizações do Telegram ) e como _callback_ da autenticação do usuário no Spotify (que leva para a URl ond está configurado o webserver, detalhada na seção **webserver**) (ambas essas URLs devem ser preenchidas no arquivo para que o bot funcione) e outras informações.

- `Dockerfile`: Arquivo do Docker explicando como formar a imagem do bot para ser usado durante a execução dos vários _containers_ através do Docker Compose.

- `requirements.txt`: Quais bibliotecas externas do python são necessárias para a execução do bot. Instaladas na imagem do bot durante a sua formação.

- `bot.py`: Arquivo que serve de ponto de entrada para a execução do bot. Aqui são checados as definições de variáveis de ambiente e do arquivo de configuração que são necessários para o funcionamento do bot (ver função 'check_config_vars()'), são definidos os _handlers_ que estarão disponíveis par o bot (associando um comando dado pelo usuário a uma função ou conjunto de funções que serão executadas) e é iniciado o processo do bot como através de um Webhook.

- `bot_general_callbacks.py`: Arquivo que reúne as funções que servem de _callback_ dos _handlers_ definidos em `bot.py`. São reunídos aqui comandos de usuários que não são do tipo 'Conversation', onde o usuário interage com o bot como se fosse numa conversa (geralmente envolvendo múltiplas funções de _callback_ para seu funcionamento), e algumas funções auxiliares. Possui as funções responsáveis pelos comandos `/start`, `/login`, `/help`, `/get_setup`,`/logout` e pelo aviso de comandos/texto não identificado.

- `bot_seed_callbacks.py`: Arquivo responsável por estabelecer a lógica de funcionamento do comando `/setup_seed`. Funciona como um tipo de conversa com o usuário, onde ele interage com o bot através de mensagens similares a menus que mostram quais _seeds_ que o usuário pode selecionar e associar a sua conta no bot (associado ao chat no qual conversa com o bot).

- `bot_survey_callbacks.py`: Arquivo responsável por estabelecer a lógica de funcionamento do comando `/setup_attributes`. Funciona como um tipo de conversa com o usuário, onde ele recebe um conjunto de mensagens, um de cada vez, pedindo para que ele selecione um nível (_level_) ou intervalo de valores (_range_) para um certo atributo que descreva a sua preferência musical (como popularidade da música, a probabilidade de possuir músicas acústicas, etc.), permitindo que ele associe essas informações a sua conta no bot (associado ao chat no qual conversa com o bot).

- `bot_playlist_callbacks.py`: Arquivo responsável por estabelecer a lógica de funcionamento do comando `/generate_playlist`. Funciona como um tipo de conversa com o usuário, onde o comando pede confirmação se o usuária quer gerar uma playlist usando os parâmetros definidos anteriormente pelos comandos `setup_seed` e `setup_attributes` (sendo que esse último pode ou não ser definido). Após confirmação, a playlist associada ao usuário é renovada com as músicas recomendadas.

- `bot_logout_callbacks.py`: Arquivo responsável por estabelecer a lógica de funcionamento do comando `/logout`. Funciona como um tipo de conversa com o usuário, onde se confirma se o usuário gostaria de proceder com a operação (deletando todos os seus dados do banco de dados interno) e, opcionalmente, deletando a playlist criada pelo bot de sua conta do Spotify.

- `spotify_survey.yaml`: Arquivo que contém informações sobre quais "perguntas" serão feitas durante o processo de seleção de atributos associado ao comando `bot_survey_callbacks`. A sua estrutura é a seguinte: um bloco são as perguntas que serão feitas, consistindo de uma lista de objetos que representam perguntas e possuem a seguinte estrutura: um campo 'text' com o texto que será apresentado ao usuário, um campo 'options\_set' apontando qual conjunto de opções será associada à essa pergunta, um campo 'attribute' que associa um nome ao atributo sendo selecionado, sendo utilizado como chave de um hash no banco de dados. O outro bloco é o das opções, consistindo de  _sets_ de opções que podem ser utilizadas durante o questionário. Cada _set_ contém um conjunto de opções, onde cada um possui um campo 'text' descrevendo a opção e um conjunto de chaves, expressando o quais os parâmetros internos e os valores reais que o usuário está selecionando quando escolhe um opção. Por exemplo, opções com chave 'target\_val' expressam opções do tipo _level_, enquanto ter chaves do tipo 'min_val' ou 'max_val' expressam opções do tipo _range_ (ver tutorial, seção **Utilizando o Bot**, subseção **Terceiro passo (opcional): Definir parâmetros para recomendação de músicas**, para mais detalhes sobre essa diferença). Esse arquivo de configuração de questionário será utilizado pela classe **SurveyManager**, definida em `/bot/backend_operations/survey.py`.



#### backend_operations

Essa pasta reúne arquivos que definem classes utilizadas como suporte às operações do bot (como se fosse um _back-end_) sob um pacote do python (_package_). Essas classes tratam da interação do bot com o Spotify e o banco de dados Redis.

- `\_\_init\_\_.py`: Arquivo vazio. Sua única função é formar um pacote com todas as classes definidas nos arquivos dessa pasta

- `redis_operations.py`: Define a classe **RedisAcess**, que serve como objeto de acesso ao banco de dados Redis associado ao bot. As maioria de seus métodos envolve formas indiretas de registrar, acessar e deletar dados associados a um certo usuário (na realidade, a associação é feita com o ID do chat onde o usuário do telegram interage com o bot, sendo ela uma espécie de chave primária). Está definida aqui também, por conveniência de acesso, o procedimento de registro dos _tokens_ recebidos do Spotify quando um usuário realiza o seu login com o comando `/login`, bem como permite a atualização do _acess token_, usado para a maior parte das operações que envolve chamadas para a API do Spotify, através do uso do _refresh token_. também são definidas classes representando erros que podem ocorrer durante o processo de obtenção dos _tokens_ do Spotify.

- `spotify_endpoint_acess.py`: Define a classe **SpotifyEndpointAcess**, que encapsula a maior parte das interações com a API do Spotify. Utiliza a classe **SpotifyRequest**, definida em `spotify_request`, como encapsulamento da operação de envio de requisições para a API do Spotify.

- `spotify_request.py`: Define a classe **SpotifyRequest**, que encapsula algumas operações envolvendo e envio de requisições para a APi do Spotify. Por exemplo, além de só enviar a requisição em si, a classe dá suporte a operações em _endpoints_ que possuem respostas paginadas e que gera erros quando a resposta da API do Spotify for uma falha.

- `survey.py`: Define a classe **SurveyManager**, responsável por interpretar as informações definidas no arquivo `spotify_survey` (na raiz do projeto) de forma a estruturar um objeto que funciona como uma máquina de estados: primeiramente está no estado que aponta para a primeira pergunta. Quando recebe o comando de ir para o próximo estado, avança o objeto para o próximo estado, que é a próxima pergunta. No meio disso, pode realizar outras operações com o objetivo de dar informações para quem possui o objeto. É utilizado durante o processo do comando `/setup_attributes`

### webserver

Essa pasta contém os arquivos necessários para rodar um servidor web usando Flask. Seu único uso é receber o código de autenticação de usuário do Spotify (através de uma chamada do tipo POST vinda da API do Spotify), salvar esse código no banco de dados Redis como valor de uma chave de 64 caracteres (hash) e mandar essa chave para o bot no Telegram através do parâmetro disponível para o comando `/start`. Há dois motivos para que simplesmente não seja enviado o código de autenticação diretamente para o bot: o número de caracteres que o comando `/start` aceita como parâmetro é no máximo 64 (e o código de autenticação é bem maior que isso) e para adicionar uma camada de segurança.

- `Dockerfile`: Gera uma imagem do Docker com o web server

- `requirements.txt`: Bibliotecas externas necessárias para a imagem do Docker

- `config.yaml`: Arquivo de configuração do webserver. Para o funcionamento do comando `/login` (sem o qual novos usuário não poderão interagir com o bot), será necessário definir o endereço (URL) do bot no Telegram. Por exemplo, se seu bot tem o _username_ "SpotSurveyTestBot", o campo seri algo como "https://telegram.me/SpotSurveyTestBot".

- `webserver.py`: Inicia um servidor usando Flask e faz a operação citada no começo dessa subseção.

### Estrutura implícita: banco de dados Redis

As chaves criadas no banco de dados Redis seguem o seguinte padrão:

- Cada usuário, após a efetuação do login, possuirá duas chaves no BD: 'user:[CHAT_ID]' e 'user:[CHAT_ID]:acess_token', onde [CHAT_ID] é o ID do chat do Telegram usado para interagir com o bot. A primeira chave possui é do representa uma entrada do tipo HASH, sendo os valores registrados nesse hash são: 'refresh_token' (o _token_ recebido do Spotify para conseguir um novo _acess token_, caso ele já tenha expirado), 'user_id' (o ID de usuário do Spotify) e 'playlist_id' (o ID da playlist criado pelo bot e que será usada preenchida com músicas recomendadas durante o processo de geração de músicas recomendadas). A segunda chave representa o _acess token_ associado ao usuário (CHAT\_ID), sendo que ela possui um tempo de vida definido pela API do Spotify onde, após esse tempo, ela é excluída do BD e deve ser reposta utilizando o _refresh token_ do usuário.

- Após a seleção das _seeds_ pelo usuário, as informações sobre os itens escolhidos são armazenados na chave 'user:[CHAT_ID]:seeds', que possui um valor do tipo HASH com duas chaves: 'tracks' para as músicas selecionadas e 'artists' para os artistas selecionados.

- Após a seleção dos atributos de músicas pelo usuário, as informações sobre as preferências do usuário são armazenadas na chave 'user:[CHAT_ID]:attributes', onde o valor associado é do tipo HASH, e as chaves existentes variam dependendo da seleção do usuário, mas em geral são chaves de mesmo nome que o campo 'attribute' das questões do formulário, descritas no arquivo `spotify_survey`. Os valores dessas 'chaves secundárias' são strings que representam um dicionário em python, igual ao dicionário associado à opção selecionada pelo usuário.

