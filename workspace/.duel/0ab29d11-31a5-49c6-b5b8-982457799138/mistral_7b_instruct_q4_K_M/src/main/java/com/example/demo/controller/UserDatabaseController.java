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
