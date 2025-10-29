Let's create the repository first.

Here is the `UserRepository.java` file:
```
File: com/example/myapp/repository/UserRepository.java
```java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface UserRepository {
    Mono<User> findById(String id);
    Flux<User> findAll();
}
```
Next, I'll create the service class. Do you want to use any specific database operations (e.g., pagination, filtering) in the `UserService` class?