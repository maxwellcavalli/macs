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
