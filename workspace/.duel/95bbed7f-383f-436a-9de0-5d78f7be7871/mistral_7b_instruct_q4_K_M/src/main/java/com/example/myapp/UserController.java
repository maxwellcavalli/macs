package com.example.myapp;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.*;

@Controller
public class UserController {

    @Autowired
    private UserService userService;

    @GetMapping("/users")
    public String listUsers(@RequestParam("page") int page, @RequestParam("size") int size, Model model) {
        model.addAttribute("page", page);
        model.addAttribute("size", size);
        return "user/list";
    }

    @GetMapping("/search")
    public String searchUsers(@RequestParam("name") String name, Model model) {
        List<User> users = userService.findByName(name);
        model.addAttribute("users", users);
        return "user/list";
    }
}
