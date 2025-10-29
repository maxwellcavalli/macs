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
