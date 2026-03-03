fn main() {
    let s1 = String::from("hello");
    let s2 = s1;
    let s3 = s1 + s2;
    println!("{} world!", s3);
}