To create a new implementation to query a user database table using R2DBC for reactive Java, follow these steps:

1. Create a new repository in your project's codebase.
2. Within the repository, create a new service class that will handle the database queries.
3. Within the service class, create a new controller class that will handle incoming requests and delegate them to the appropriate methods in the service class.
4. Keep the attached file folder organization (package) for your project's files.

Here is an example of how you might structure your code:
```java
// Repository
// src/main/java/com/example/myproject/repository/UserDatabaseService.java

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface UserDatabaseService {
    Flux<User> getAllUsers();
    Mono<User> getUserById(Long id);
}
```

```java
// Repository
// src/main/java/com/example/myproject/repository/UserDatabaseController.java

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.netty.http.server.HttpServer;
import reactor.netty.http.server.WebSocketHandler;
import reactor.netty.http.server.WebSocketSession;

public class UserDatabaseController {
    private final UserDatabaseService userDatabaseService;

    public UserDatabaseController(UserDatabaseService userDatabaseService) {
        this.userDatabaseService = userDatabaseService;
    }

    @WebSocketHandler
    public Mono<Void> handleWebSocketConnection(WebSocketSession session) {
        return session.receive()
                .flatMap(message -> message.bodyAsText())
                .map(request -> request.split(" "))
                .filter(parts -> parts[0].equalsIgnoreCase("GET"))
                .flatMap(parts -> {
                    String path = parts[1];
                    if (path.equalsIgnoreCase("/users")) {
                        return userDatabaseService.getAllUsers();
                    } else if (path.startsWith("/users/")) {
                        Long id = Long.parseLong(parts[2].substring(1));
                        return userDatabaseService.getUserById(id);
                    }
                    return Mono.empty();
                })
                .doOnNext(response -> session.sendText(response))
                .doOnError(error -> session.sendText("Error: " + error.getMessage()));
    }
}
```

```java
// Repository
// src/main/java/com/example/myproject/repository/UserDatabaseServiceImpl.java

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.netty.http.client.HttpClient;
import reactor.netty.http.client.HttpRequest;
import reactor.netty.http.client.HttpResponse;
import reactor.netty.http.client.WebSocketClient;

public class UserDatabaseServiceImpl implements UserDatabaseService {
    private final HttpClient httpClient = HttpClient.create();
    private final WebSocketClient webSocketClient = WebSocketClient.create();

    @Override
    public Flux<User> getAllUsers() {
        return webSocketClient.connect("ws://localhost:8080/users")
                .flatMap(session -> session.receive().map(message -> message.bodyAsText()))
                .doOnNext(response -> System.out.println("Received response: " + response))
                .map(response -> User.fromJson(response));
    }

    @Override
    public Mono<User> getUserById(Long id) {
        return webSocketClient.connect("ws://localhost:8080/users/" + id)
                .flatMap(session -> session.receive().map(message -> message.bodyAsText()))
                .doOnNext(response -> System.out.println("Received response: " + response))
                .map(response -> User.fromJson(response));
    }
}
```

In this example, the `UserDatabaseServiceImpl` class implements the `UserDatabaseService` interface and uses R2DBC to connect to a local web socket server running on port 8080. The `UserDatabaseController` class handles incoming requests and delegates them to the appropriate methods in the `UserDatabaseServiceImpl` class.

Note that this is just an example implementation, and you may need to modify it to fit your specific use case.