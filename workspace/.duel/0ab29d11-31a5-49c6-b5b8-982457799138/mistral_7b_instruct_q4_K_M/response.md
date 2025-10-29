To create a new implementation to query a user database table using R2DBC for reactive Java, follow these steps:

1. Create a new repository in your project's source code management system (e.g., GitHub).
2. Within the repository, create a new service class that will handle the database queries. This class should extend `ReactorDatabaseClient` and implement the necessary methods to query the user table using R2DBC.
3. Create a new controller class that will handle incoming HTTP requests and delegate the querying of the user table to the service class. This class should use Spring WebFlux or another reactive web framework to handle the request-response cycle.
4. Ensure that your project's build configuration (e.g., `build.gradle` or `pom.xml`) includes the necessary dependencies for R2DBC and any other libraries required by your implementation.
5. Organize your code into packages based on their functionality, following the folder structure you provided in your previous message.

Here's an example of what a service class might look like:
```java
import reactor.core.publisher.Flux;
import org.springframework.stereotype.Service;
import org.springframework.data.r2dbc.repository.R2dbcRepository;
import org.springframework.data.r2dbc.repository.R2dbcQuery;

@Service
public class UserDatabaseService extends R2dbcRepository<User, Long> {

    @Override
    public Flux<User> findAll() {
        return query("SELECT * FROM user")
                .bindToReactorTable(User.class)
                .doOnNext(user -> System.out.println("Found user: " + user));
    }
}
```
And here's an example of what a controller class might look like:
```java
import reactor.core.publisher.Mono;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.BodyInserters;

@RestController
public class UserDatabaseController {

    @Autowired
    private UserDatabaseService userDatabaseService;

    @GetMapping("/users")
    public ResponseEntity<Flux<User>> getAllUsers() {
        return new ResponseEntity<>(userDatabaseService.findAll(), HttpStatus.OK);
    }
}
```
Please let me know if you need more information or have any questions about these examples!