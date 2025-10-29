
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
