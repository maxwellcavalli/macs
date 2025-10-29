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
