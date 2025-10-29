To create a repository, service, and connect it to a controller to query users using R2DBC, you can follow these steps:

1. Create a new Spring Boot project with the Web and Reactive dependencies. You can do this by running the following command in your terminal:
```bash
curl https://start.spring.io/starter.zip -o myproject.zip
unzip myproject.zip
cd myproject
```
2. Add the R2DBC dependency to your `pom.xml` file by adding the following line inside the `<dependencies>` tag:
```xml
<dependency>
    <groupId>org.springframework.data</groupId>
    <artifactId>r2dbc-core</artifactId>
    <version>1.0.11.RELEASE</version>
</dependency>
```
3. Create a new package named `repository` inside your project's main package. Inside this package, create a new class called `UserRepository`. This class will implement the `UserRepository` interface provided by Spring Data R2DBC.
4. In the `UserRepository` class, you can define methods for querying users using R2DBC. For example:
```java
import org.springframework.data.r2dbc.repository.R2dbcRepository;
import reactor.core.publisher.Flux;

public interface UserRepository extends R2dbcRepository<User, Long> {
    Flux<User> findAll();
}
```
5. Create a new package named `service` inside your project's main package. Inside this package, create a new class called `UserService`. This class will implement the `UserService` interface provided by Spring Data R2DBC.
6. In the `UserService` class, you can define methods for querying users using the `UserRepository`. For example:
```java
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;

@Service
public class UserService {
    @Autowired
    private UserRepository userRepository;

    public Flux<User> getAllUsers() {
        return userRepository.findAll();
    }
}
```
7. Create a new package named `controller` inside your project's main package. Inside this package, create a new class called `UserController`. This class will implement the `UserController` interface provided by Spring Data R2DBC.
8. In the `UserController` class, you can define methods for querying users using the `UserService`. For example:
```java
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.GetMapping;
import reactor.core.publisher.Flux;

@RestController
public class UserController {
    @Autowired
    private UserService userService;

    @GetMapping("/users")
    public Flux<User> getAllUsers() {
        return userService.getAllUsers();
    }
}
```
9. Run your Spring Boot application by running the following command in your terminal:
```bash
./mvnw spring-boot:run
```
10. You can now query users using R2DBC by sending a GET request to `http://localhost:8080/users`.

That's it! You have created a repository, service, and connected it to a controller to query users using R2DBC in Spring Boot.