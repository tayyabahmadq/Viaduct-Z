# Retrofit + kotlinx.serialization keeps its generated serializers; no rules needed
# while minification is off. Kept so `release` has a file to point at.
-keepattributes *Annotation*, InnerClasses
-dontnote kotlinx.serialization.**
