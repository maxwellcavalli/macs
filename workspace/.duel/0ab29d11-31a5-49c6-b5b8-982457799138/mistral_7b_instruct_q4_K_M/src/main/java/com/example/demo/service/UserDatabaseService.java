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
