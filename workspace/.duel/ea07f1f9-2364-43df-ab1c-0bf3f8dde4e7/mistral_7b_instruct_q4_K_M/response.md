File: src/main/java/com/example/myapp/repository/UserRepository.java
```typescript
import com.example.myapp.model.User;
import org.springframework.data.r2dbc.repository.R2dbcRepository;

public interface UserRepository extends R2dbcRepository<User, String> {
}
```
File: src/main/java/com/example/myapp/service/UserService.java
```typescript
import com.example.myapp.repository.UserRepository;
import com.example.myapp.model.User;
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
File: src/main/java/com/example/myapp/controller/UserController.java
```typescript
import com.example.myapp.service.UserService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
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