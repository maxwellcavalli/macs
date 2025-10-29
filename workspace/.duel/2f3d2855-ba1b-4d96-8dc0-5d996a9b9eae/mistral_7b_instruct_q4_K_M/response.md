File: src/main/java/com/example/myapp/repository/UserRepository.java
```java
import com.example.myapp.model.User;
import reactor.core.publisher.Flux;

public interface UserRepository extends ReactiveCrudRepository<User, Long> {
}
```
File: src/main/java/com/example/myapp/service/UserService.java
```java
import com.example.myapp.repository.UserRepository;
import com.example.myapp.model.User;
import reactor.core.publisher.Flux;

public class UserService {
    private final UserRepository userRepository;

    public UserService(UserRepository userRepository) {
        this.userRepository = userRepository;
    }

    public Flux<User> getAllUsers() {
        return userRepository.findAll();
    }
}
```
File: src/main/java/com/example/myapp/controller/UserController.java
```java
import com.example.myapp.service.UserService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class UserController {
    private final UserService userService;

    @Autowired
    public UserController(UserService userService) {
        this.userService = userService;
    }

    @GetMapping("/users")
    public Flux<User> getAllUsers() {
        return userService.getAllUsers();
    }
}
```
File: src/main/java/com/example/myapp/config/AppConfig.java
```java
import com.example.myapp.repository.UserRepository;
import com.example.myapp.service.UserService;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import reactor.netty.http.client.HttpClient;
import reactor.netty.http.client.ReactorNettyHttpClient;
import reactor.netty.http.client.server.ServerHttpClient;
import reactor.netty.http.client.server.ServerHttpClientBuilder;

@Configuration
public class AppConfig {
    @Bean
    public UserRepository userRepository() {
        return new UserRepository();
    }

    @Bean
    public UserService userService(UserRepository userRepository) {
        return new UserService(userRepository);
    }

    @Bean
    public HttpClient httpClient() {
        return new ReactorNettyHttpClient();
    }

    @Bean
    public ServerHttpClient serverHttpClient() {
        return new ServerHttpClientBuilder()
                .httpClient(httpClient())
                .port(8080)
                .build();
    }
}
```