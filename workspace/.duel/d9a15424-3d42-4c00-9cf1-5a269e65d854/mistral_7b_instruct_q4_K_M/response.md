To create a new implementation to query a user database table using R2DBC for reactive Java, follow these steps:

1. Create a new repository in your project's source control system.
2. Within the repository, create a new service class that will handle the database queries. This class should extend `ReactorDatabaseClient` and implement methods to query the user table using R2DBC.
3. Create a new controller class that will handle incoming HTTP requests and delegate the querying of the user table to the service class.
4. Keep the attached file folder organization (package) for your project's code files.

Here is an example implementation of a `UserService` class:
```java
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class UserService extends ReactorDatabaseClient {

    private final String userTableName = "user_table";

    public Flux<User> getAllUsers() {
        return query(userTableName, "SELECT * FROM user_table")
                .map(row -> new User(row.getInt("id"), row.getString("name"), row.getString("email")))
                .doOnNext(this::logUser);
    }

    private void logUser(User user) {
        System.out.println("Retrieved user: " + user);
    }
}
```
And here is an example implementation of a `UserController` class:
```java
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/users")
public class UserController {

    @Autowired
    private UserService userService;

    @GetMapping
    public ResponseEntity<Flux<User>> getAllUsers() {
        return new ResponseEntity<>(userService.getAllUsers(), HttpStatus.OK);
    }
}
```
Please let me know if you need more information or have any questions about this implementation.