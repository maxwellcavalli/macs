package com.example.myapp;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;

@Controller
public class UserController {
    @GetMapping("/users")
    public String getUsers(@RequestParam("id") int id) {
        // Query the user table and return results here
    }
}
