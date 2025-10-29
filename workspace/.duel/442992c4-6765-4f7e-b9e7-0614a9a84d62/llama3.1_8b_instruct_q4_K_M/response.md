Let's get started. For this example, I'll assume we're using Spring Boot with R2DBC.

First, let's create the repository. We'll use `UserRepository` as the interface and implement it with `R2dbcUserRepository`.

Here are the files:

**user/repository/UserRepository.java**
```java
File: src/main/java/com/example/user/repository/UserRepository.java

public interface UserRepository extends JpaRepository<User, Long> {
    Flux<User> findByUsername(String username);
}
```

**user/repository/R2dbcUserRepository.java**
```java
File: src/main/java/com/example/user/repository/R2dbcUserRepository.java

import io.r2dbc.spi.Row;
import reactor.core.publisher.Flux;

public class R2dbcUserRepository implements UserRepository {
    @Override
    public Flux<User> findByUsername(String username) {
        // Implement query using R2DBC
        return Flux.from(r2dbcTemplate.select("SELECT * FROM users WHERE username = :username")
                .parameter("username", username)
                .fetch().all());
    }
}
```

Next, I'll create the service. We'll use `UserService` as the interface and implement it with `R2dbcUserService`.

Do you want to proceed with creating the service?